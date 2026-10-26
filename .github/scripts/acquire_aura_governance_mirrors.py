#!/usr/bin/env python3
"""Acquire read-only Git mirrors and bundles for AURA governance forensics.

This program does not check out or execute source from either target repository.
It records the bytes returned by the Git transport, preserves advertised refs and
attempts the hosting platforms' pull/merge-request refs as supplemental evidence.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import tarfile
import time

ROOT = Path("acquisition-work")
MIRRORS = ROOT / "mirrors"
BUNDLES = ROOT / "bundles"
LOGS = ROOT / "logs"
INVENTORY = ROOT / "inventory"
DIST = Path("dist")

REPOSITORIES = [
    {
        "key": "github",
        "platform": "GitHub",
        "url": "https://github.com/vaidt/aura-specification.git",
        "project": "vaidt/aura-specification",
        "supplemental_refspecs": [
            "+refs/pull/*/head:refs/pull/*/head",
            "+refs/pull/*/merge:refs/pull/*/merge",
        ],
        "supplemental_scope": "GitHub pull-request head and merge refs, when fetchable",
    },
    {
        "key": "gitlab",
        "platform": "GitLab",
        "url": "https://gitlab.com/vaidt/aura-specification.git",
        "project": "vaidt/aura-specification",
        "supplemental_refspecs": [
            "+refs/merge-requests/*/head:refs/merge-requests/*/head",
            "+refs/merge-requests/*/merge:refs/merge-requests/*/merge",
        ],
        "supplemental_scope": "GitLab merge-request head and merge refs, when fetchable",
    },
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_command(command: list[str], log_stem: Path, cwd: Path | None = None) -> dict:
    started = utc_now()
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=GIT_ENV,
            check=False,
            timeout=900,
        )
        stdout = completed.stdout
        stderr = completed.stderr
        rc = completed.returncode
    except Exception as exc:
        stdout = b""
        stderr = (type(exc).__name__ + ": " + str(exc)).encode("utf-8", errors="replace")
        rc = 127
    log_stem.parent.mkdir(parents=True, exist_ok=True)
    out_path = log_stem.with_suffix(".stdout.raw")
    err_path = log_stem.with_suffix(".stderr.raw")
    out_path.write_bytes(stdout)
    err_path.write_bytes(stderr)
    return {
        "command": shlex.join(command),
        "cwd": str(cwd) if cwd else None,
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "exit_code": rc,
        "stdout_path": out_path.as_posix(),
        "stdout_sha256": sha256_bytes(stdout),
        "stdout_size_bytes": len(stdout),
        "stderr_path": err_path.as_posix(),
        "stderr_sha256": sha256_bytes(stderr),
        "stderr_size_bytes": len(stderr),
    }


def parse_ls_remote(data: bytes) -> list[dict]:
    refs = []
    for raw_line in data.decode("utf-8", errors="replace").splitlines():
        parts = raw_line.split("\t", 1)
        if len(parts) != 2:
            continue
        oid, ref = parts
        if ref == "HEAD" and oid.startswith("ref: "):
            refs.append({"ref": "HEAD", "symref_target": oid[5:], "object_id": None})
        elif len(oid) in (40, 64) and all(c in "0123456789abcdef" for c in oid.lower()):
            refs.append({"ref": ref, "symref_target": None, "object_id": oid.lower()})
    return refs


def safe_relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def inventory_tree(root: Path) -> list[dict]:
    rows = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows.append({"path": rel, "kind": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            rows.append({
                "path": rel,
                "kind": "file",
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            })
    return rows


def main() -> int:
    started_at = utc_now()
    for directory in (MIRRORS, BUNDLES, LOGS, INVENTORY, DIST):
        directory.mkdir(parents=True, exist_ok=True)
    empty_global_config = ROOT / "empty-git-global-config"
    empty_global_config.write_bytes(b"")
    global GIT_ENV
    GIT_ENV = os.environ.copy()
    GIT_ENV.update({
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": str(empty_global_config.resolve()),
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TRACE": "0",
        "GIT_TRACE_SETUP": "0",
        "GIT_TRACE_PACKET": "0",
    })

    run_id = os.environ.get("GITHUB_RUN_ID", "local")
    attempt = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
    workflow_sha = os.environ.get("GITHUB_SHA", "UNAVAILABLE")
    workflow_ref = os.environ.get("GITHUB_WORKFLOW_REF", "UNAVAILABLE")
    repository_id = os.environ.get("GITHUB_REPOSITORY", "UNAVAILABLE")

    repo_results = []
    fatal_errors = []
    for spec in REPOSITORIES:
        key = spec["key"]
        mirror = MIRRORS / f"{key}-aura-specification.git"
        bundle = BUNDLES / f"{key}-aura-specification.bundle"
        per_repo = {
            "key": key,
            "platform": spec["platform"],
            "project": spec["project"],
            "remote_url": spec["url"],
            "advertised_refs": [],
            "operations": {},
            "supplemental_ref_fetches": [],
            "mirror_path": safe_relative(mirror),
            "bundle_path": safe_relative(bundle),
        }

        ls_path = LOGS / key / "ls-remote"
        ls_result = run_command(["git", "ls-remote", "--symref", spec["url"]], ls_path)
        per_repo["operations"]["ls_remote"] = ls_result
        raw_ls_path = Path(ls_result["stdout_path"])
        per_repo["advertised_refs"] = parse_ls_remote(raw_ls_path.read_bytes())
        per_repo["advertised_ref_count"] = sum(
            1 for ref in per_repo["advertised_refs"] if ref["object_id"] is not None
        )
        if ls_result["exit_code"] != 0:
            fatal_errors.append(f"{key}: git ls-remote failed with {ls_result['exit_code']}")

        clone_path = LOGS / key / "clone-mirror"
        clone_result = run_command(
            ["git", "clone", "--mirror", "--no-hardlinks", spec["url"], str(mirror.resolve())],
            clone_path,
        )
        per_repo["operations"]["clone_mirror"] = clone_result
        if clone_result["exit_code"] != 0:
            fatal_errors.append(f"{key}: git clone --mirror failed with {clone_result['exit_code']}")
            repo_results.append(per_repo)
            continue

        # Host-specific hidden refs are supplemental; failures are recorded, not silently ignored.
        for number, refspec in enumerate(spec["supplemental_refspecs"], start=1):
            stem = LOGS / key / f"supplemental-fetch-{number}"
            result = run_command(
                ["git", "-C", str(mirror), "fetch", "--force", "--no-tags", "origin", refspec],
                stem,
            )
            per_repo["supplemental_ref_fetches"].append({
                "refspec": refspec,
                "result": result,
                "status": "FETCHED" if result["exit_code"] == 0 else "UNAVAILABLE_OR_REJECTED",
            })

        # Freeze full ref/object inventory after clone and supplemental refs.
        refs_result = run_command(
            ["git", "-C", str(mirror), "for-each-ref", "--format=%(refname)%09%(objectname)%09%(objecttype)"],
            LOGS / key / "local-refs",
        )
        per_repo["operations"]["local_refs"] = refs_result
        refs_bytes = (Path(refs_result["stdout_path"])).read_bytes()
        ref_lines = refs_bytes.decode("utf-8", errors="replace").splitlines()
        ref_inventory = []
        for line in ref_lines:
            parts = line.split("\t")
            if len(parts) == 3:
                ref_inventory.append({"ref": parts[0], "object_id": parts[1], "object_type": parts[2]})
        per_repo["local_ref_count"] = len(ref_inventory)
        per_repo["local_refs_path"] = safe_relative(Path(refs_result["stdout_path"]))
        per_repo["local_refs_sha256"] = sha256_bytes(refs_bytes)
        per_repo["local_refs"] = ref_inventory

        symref_result = run_command(
            ["git", "-C", str(mirror), "symbolic-ref", "-q", "HEAD"],
            LOGS / key / "mirror-head-symref",
        )
        per_repo["operations"]["mirror_head_symref"] = symref_result
        if symref_result["exit_code"] == 0:
            per_repo["mirror_head_symref"] = Path(symref_result["stdout_path"]).read_text(encoding="utf-8", errors="replace").strip()
        else:
            per_repo["mirror_head_symref"] = None

        oid_result = run_command(
            ["git", "-C", str(mirror), "rev-parse", "--verify", "HEAD"],
            LOGS / key / "mirror-head-oid",
        )
        per_repo["operations"]["mirror_head_oid"] = oid_result
        per_repo["mirror_head_oid"] = Path(oid_result["stdout_path"]).read_text(encoding="ascii", errors="replace").strip() if oid_result["exit_code"] == 0 else None

        count_result = run_command(
            ["git", "-C", str(mirror), "rev-list", "--all", "--count"],
            LOGS / key / "reachable-commit-count",
        )
        per_repo["operations"]["reachable_commit_count"] = count_result
        try:
            per_repo["reachable_commit_count"] = int(Path(count_result["stdout_path"]).read_text(encoding="ascii").strip())
        except Exception:
            per_repo["reachable_commit_count"] = None

        object_format = run_command(["git", "-C", str(mirror), "rev-parse", "--show-object-format"], LOGS / key / "object-format")
        per_repo["operations"]["object_format"] = object_format
        per_repo["object_format"] = Path(object_format["stdout_path"]).read_text(encoding="ascii", errors="replace").strip() if object_format["exit_code"] == 0 else None

        fsck = run_command(
            ["git", "-C", str(mirror), "fsck", "--full", "--strict", "--no-reflogs"],
            LOGS / key / "fsck",
        )
        per_repo["operations"]["fsck"] = fsck
        per_repo["fsck_status"] = "PASS" if fsck["exit_code"] == 0 else "ERROR_RECORDED"
        if fsck["exit_code"] != 0:
            fatal_errors.append(f"{key}: git fsck failed with {fsck['exit_code']}")
        # Preserve diagnostics and the bundle even when fsck blocks completion.
        bundle_result = run_command(
            ["git", "-C", str(mirror), "bundle", "create", str(bundle.resolve()), "--all"],
            LOGS / key / "bundle-create",
        )
        per_repo["operations"]["bundle_create"] = bundle_result
        if bundle_result["exit_code"] != 0 or not bundle.is_file():
            fatal_errors.append(f"{key}: git bundle create failed")
            repo_results.append(per_repo)
            continue

        bundle_verify = run_command(
            ["git", "bundle", "verify", str(bundle.resolve())],
            LOGS / key / "bundle-verify",
        )
        per_repo["operations"]["bundle_verify"] = bundle_verify
        per_repo["bundle_verify_status"] = "PASS" if bundle_verify["exit_code"] == 0 else "FAIL"
        if bundle_verify["exit_code"] != 0:
            fatal_errors.append(f"{key}: git bundle verify failed")

        bundle_heads = run_command(["git", "bundle", "list-heads", str(bundle.resolve())], LOGS / key / "bundle-heads")
        per_repo["operations"]["bundle_heads"] = bundle_heads
        per_repo["bundle_path_sha256"] = sha256_file(bundle)
        per_repo["bundle_size_bytes"] = bundle.stat().st_size
        per_repo["bundle_heads_path"] = safe_relative(Path(bundle_heads["stdout_path"]))
        per_repo["bundle_heads_sha256"] = bundle_heads["stdout_sha256"]

        # Full bare mirror is retained as well as the portable bundle.
        per_repo["mirror_ref_inventory_sha256"] = sha256_bytes(refs_bytes)
        per_repo["mirror_directory_file_count"] = sum(1 for p in mirror.rglob("*") if p.is_file() or p.is_symlink())
        repo_results.append(per_repo)

    manifest = {
        "schema": "aura.governance-raw-mirror-acquisition/0.1.0",
        "classification": "READ_ONLY / FORENSIC / NON_CONSTITUTIVE",
        "created_by_workflow": repository_id,
        "workflow_path": os.environ.get("WORKFLOW_PATH", ".github/workflows/governance-raw-mirror-acquisition.yml"),
        "workflow_ref": workflow_ref,
        "workflow_commit_sha": workflow_sha,
        "run_id": run_id,
        "run_attempt": attempt,
        "acquisition_started_at_utc": started_at,
        "acquisition_completed_at_utc": utc_now(),
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "git_version": subprocess.run(["git", "--version"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=GIT_ENV, check=False).stdout.decode("utf-8", errors="replace").strip(),
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
        },
        "repositories": repo_results,
        "fatal_errors": fatal_errors,
        "limits": [
            "The acquisition contains refs advertised by public Git transport and supplemental pull/merge-request refs that the server permits fetching.",
            "Git bundles contain objects reachable from included refs. Hidden server objects, server-side reflogs, deleted unadvertised refs, and hosting audit logs are outside this acquisition boundary.",
            "A successful bundle verification establishes transport-level Git object consistency, not authority, identity, ratification, or normative effect.",
            "No code from either target repository is checked out into a working tree or executed by this workflow.",
            "The local metadata reports and their hashes are an acquisition record; trust in the acquisition workflow is evaluated separately through GitHub Actions attestations.",
        ],
        "acquisition_status": "COMPLETE_ADVERTISED_REFS" if not fatal_errors else "BLOCKED",
    }

    # Complete per-file hash inventory before writing the manifest itself.
    manifest["files"] = inventory_tree(ROOT)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_path = ROOT / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_digest = sha256_bytes(manifest_bytes)
    (ROOT / "manifest.sha256").write_text(f"{manifest_digest}  manifest.json\n", encoding="ascii")

    DIST.mkdir(parents=True, exist_ok=True)
    archive = DIST / f"AURA_GOVERNANCE_RAW_MIRROR_ACQUISITION_{run_id}_attempt_{attempt}.tar.gz"
    with tarfile.open(archive, mode="w:gz", compresslevel=9) as tf:
        tf.add(ROOT, arcname="acquisition", recursive=True)
    archive_digest = sha256_file(archive)
    sidecar = DIST / (archive.name + ".sha256")
    sidecar.write_text(f"{archive_digest}  {archive.name}\n", encoding="ascii")
    receipt = {
        "schema": "aura.governance-acquisition-receipt/0.1.0",
        "archive": archive.name,
        "archive_sha256": archive_digest,
        "archive_size_bytes": archive.stat().st_size,
        "manifest_sha256": manifest_digest,
        "run_id": run_id,
        "run_attempt": attempt,
        "workflow_commit_sha": workflow_sha,
        "acquisition_status": manifest["acquisition_status"],
        "fatal_errors": fatal_errors,
        "repository_summary": [
            {
                "key": row["key"],
                "remote_url": row["remote_url"],
                "advertised_ref_count": row.get("advertised_ref_count"),
                "local_ref_count": row.get("local_ref_count"),
                "reachable_commit_count": row.get("reachable_commit_count"),
                "mirror_head_oid": row.get("mirror_head_oid"),
                "bundle_path_sha256": row.get("bundle_path_sha256"),
                "bundle_verify_status": row.get("bundle_verify_status"),
                "fsck_status": row.get("fsck_status"),
            }
            for row in repo_results
        ],
        "historical_receipts_modified": False,
        "target_repositories_modified": False,
        "normative_effect": "NONE",
    }
    Path("dist/acquisition-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if not fatal_errors and all(r.get("bundle_verify_status") == "PASS" for r in repo_results) and len(repo_results) == 2 else 20


if __name__ == "__main__":
    raise SystemExit(main())
