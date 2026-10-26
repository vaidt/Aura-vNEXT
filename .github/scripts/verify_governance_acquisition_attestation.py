#!/usr/bin/env python3
"""Independent fail-closed verification of a signed AURA raw-mirror acquisition.

Cryptographic signature/trust checks are performed by gh attestation verify.
This program independently checks the CLI outputs, identity/invocation bindings,
archive digest, embedded manifest, every acquired file hash, and Git ref/bundle
inventory consistency. It never executes or extracts target repository code.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tarfile

SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
CUSTOM_PREDICATE = "https://github.com/vaidt/Aura-vNEXT/attestations/aura-governance-raw-mirror-acquisition/v1"
EXPECTED_REPOSITORIES = {
    "github": "https://github.com/vaidt/aura-specification.git",
    "gitlab": "https://gitlab.com/vaidt/aura-specification.git",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def walk(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from walk(nested)


def find_verification(value, predicate_type: str) -> dict | None:
    for item in walk(value):
        if not isinstance(item, dict):
            continue
        vr = item.get("verificationResult")
        if isinstance(vr, dict):
            statement = vr.get("statement")
            if isinstance(statement, dict) and statement.get("predicateType") == predicate_type:
                return vr
    for item in walk(value):
        if isinstance(item, dict) and item.get("predicateType") == predicate_type and "subject" in item and "predicate" in item:
            return {"statement": item}
    return None


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from strings(nested)


def certificate_details(verification: dict, expected_identity: str) -> dict:
    signature = verification.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("verified CLI result lacks signature object")
    cert = signature.get("certificate")
    if not isinstance(cert, dict) or not cert:
        raise ValueError("verified CLI result lacks signing certificate")
    cert_strings = list(strings(cert))
    issuer_ok = any("token.actions.githubusercontent.com" in value for value in cert_strings)
    san_candidates = []
    for key in ("san", "subjectAlternativeName", "subject_alternative_name", "subjectAltName"):
        if key in cert:
            san_candidates.extend(list(strings(cert[key])))
    if not san_candidates:
        san_candidates = [value for value in cert_strings if "github.com/vaidt/Aura-vNEXT/.github/workflows/" in value]
    matched = [value for value in san_candidates if expected_identity in value]
    timestamps = verification.get("verifiedTimestamps")
    if timestamps is None:
        timestamps = verification.get("verified_timestamps")
    timestamp_count = len(timestamps) if isinstance(timestamps, list) else 0
    if not issuer_ok:
        raise ValueError("certificate does not identify the GitHub Actions OIDC issuer")
    if not matched:
        raise ValueError("certificate SAN is not bound to the expected repository/workflow/ref")
    if timestamp_count < 1:
        raise ValueError("CLI result has no verified transparency timestamp")
    return {
        "status": "PASS",
        "issuer_match": True,
        "certificate_identity": matched[0],
        "verified_timestamp_count": timestamp_count,
        "certificate_fields_observed": sorted(cert.keys()),
    }


def selected_repo_fields(repo: dict) -> dict:
    return {
        "key": repo.get("key"),
        "platform": repo.get("platform"),
        "project": repo.get("project"),
        "remote_url": repo.get("remote_url"),
        "advertised_ref_count": repo.get("advertised_ref_count"),
        "local_ref_count": repo.get("local_ref_count"),
        "reachable_commit_count": repo.get("reachable_commit_count"),
        "mirror_head_symref": repo.get("mirror_head_symref"),
        "mirror_head_oid": repo.get("mirror_head_oid"),
        "local_refs_sha256": repo.get("local_refs_sha256"),
        "bundle_path_sha256": repo.get("bundle_path_sha256"),
        "bundle_verify_status": repo.get("bundle_verify_status"),
        "fsck_status": repo.get("fsck_status"),
        "supplemental_ref_fetches": [
            {"refspec": item.get("refspec"), "status": item.get("status")}
            for item in repo.get("supplemental_ref_fetches", [])
        ],
    }


def parse_advertised_transport(data: bytes) -> list[dict]:
    """Independently decode the complete ls-remote --symref stdout; reject ambiguity."""
    rows = []
    seen = set()
    for line in data.decode("utf-8", errors="strict").splitlines():
        fields = line.split("\t")
        if len(fields) != 2:
            raise ValueError("malformed ls-remote transport record")
        value, ref = fields
        if value.startswith("ref: ") and ref == "HEAD" and value[5:].startswith("refs/"):
            row = {"ref": ref, "symref_target": value[5:], "object_id": None}
        elif re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", value) and (ref == "HEAD" or ref.startswith("refs/")):
            row = {"ref": ref, "symref_target": None, "object_id": value.lower()}
        else:
            raise ValueError("invalid ls-remote transport record")
        identity = (ref, row["object_id"] is None)
        if identity in seen:
            raise ValueError("duplicate ls-remote transport record")
        seen.add(identity)
        rows.append(row)
    if not rows:
        raise ValueError("empty advertised-ref transport")
    return rows


def verify_archive(archive: Path, sidecar: Path, expected: dict) -> dict:
    archive_digest = sha256_file(archive)
    sidecar_match = re.fullmatch(
        r"([0-9a-f]{64})\s+\*?([^\r\n]+)\s*\n?",
        sidecar.read_text(encoding="ascii"),
    )
    if not sidecar_match or sidecar_match.group(1) != archive_digest or Path(sidecar_match.group(2)).name != archive.name:
        raise ValueError("external archive SHA-256 sidecar mismatch")

    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise ValueError("tar contains duplicate member names")
        content_map = {}
        for member in members:
            name = member.name
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name:
                raise ValueError(f"unsafe tar path {name!r}")
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise ValueError(f"non-regular archive member refused: {name!r}")
            if member.isfile():
                stream = tf.extractfile(member)
                if stream is None:
                    raise ValueError(f"cannot read archive member {name!r}")
                content_map[name] = stream.read()

    base = "acquisition/"
    manifest_name = base + "manifest.json"
    checksum_name = base + "manifest.sha256"
    if manifest_name not in content_map or checksum_name not in content_map:
        raise ValueError("archive lacks embedded manifest.json or manifest.sha256")
    manifest_bytes = content_map[manifest_name]
    manifest_digest = sha256_bytes(manifest_bytes)
    if content_map[checksum_name].decode("ascii").strip() != f"{manifest_digest}  manifest.json":
        raise ValueError("embedded manifest checksum mismatch")
    manifest = json.loads(manifest_bytes)
    if manifest.get("schema") != "aura.governance-raw-mirror-acquisition/0.1.0":
        raise ValueError("unsupported manifest schema")
    if manifest.get("classification") != "READ_ONLY / FORENSIC / NON_CONSTITUTIVE":
        raise ValueError("unexpected acquisition classification")
    if manifest.get("acquisition_status") != "COMPLETE_ADVERTISED_REFS":
        raise ValueError("acquisition is not COMPLETE_ADVERTISED_REFS")

    if manifest.get("fatal_errors") != []:
        raise ValueError("acquisition has fatal errors or lacks fatal_errors")

    file_inventory = manifest.get("files")
    if not isinstance(file_inventory, list):
        raise ValueError("manifest file inventory missing")
    expected_member_names = {base + entry["path"] for entry in file_inventory}
    actual_payload_names = set(content_map) - {manifest_name, checksum_name}
    if expected_member_names != actual_payload_names:
        raise ValueError("manifest file inventory does not exactly match archive members")

    for entry in file_inventory:
        name = entry.get("path")
        archive_name = base + str(name)
        content = content_map.get(archive_name)
        if entry.get("kind") == "symlink":
            raise ValueError(f"unexpected symlink recorded in acquisition payload: {name}")
        if entry.get("kind") != "file" or content is None:
            raise ValueError(f"invalid or missing file inventory entry: {name}")
        if entry.get("size_bytes") != len(content) or entry.get("sha256") != sha256_bytes(content):
            raise ValueError(f"file manifest hash/size mismatch for {name}")

    repositories = manifest.get("repositories")
    if not isinstance(repositories, list) or len(repositories) != 2:
        raise ValueError("manifest must contain exactly the GitHub and GitLab repositories")
    by_key = {row.get("key"): row for row in repositories}
    if set(by_key) != set(EXPECTED_REPOSITORIES):
        raise ValueError("unexpected or missing repository keys")

    repo_reports = []
    for key, expected_url in EXPECTED_REPOSITORIES.items():
        repo = by_key[key]
        if repo.get("remote_url") != expected_url:
            raise ValueError(f"{key}: remote URL differs from expected public repository")
        if repo.get("operations", {}).get("ls_remote", {}).get("exit_code") != 0:
            raise ValueError(f"{key}: ls-remote failed")
        ls_operation = repo["operations"]["ls_remote"]
        raw_path = ls_operation.get("stdout_path")
        prefix = "acquisition-work/"
        if not isinstance(raw_path, str) or not raw_path.startswith(prefix):
            raise ValueError(f"{key}: invalid ls-remote stdout path")
        raw_transport = content_map.get(base + raw_path[len(prefix):])
        if raw_transport is None:
            raise ValueError(f"{key}: ls-remote transport log missing")
        if (ls_operation.get("stdout_sha256") != sha256_bytes(raw_transport)
                or ls_operation.get("stdout_size_bytes") != len(raw_transport)):
            raise ValueError(f"{key}: ls-remote transport digest/size mismatch")
        advertised_rows = parse_advertised_transport(raw_transport)
        if advertised_rows != repo.get("advertised_refs"):
            raise ValueError(f"{key}: advertised refs differ from raw transport")
        if sum(row["object_id"] is not None for row in advertised_rows) != repo.get("advertised_ref_count"):
            raise ValueError(f"{key}: advertised ref count mismatch")
        if (repo.get("fsck_status") != "PASS"
                or repo.get("operations", {}).get("fsck", {}).get("exit_code") != 0):
            raise ValueError(f"{key}: git fsck did not pass")
        if repo.get("operations", {}).get("clone_mirror", {}).get("exit_code") != 0:
            raise ValueError(f"{key}: mirror clone failed")
        if repo.get("operations", {}).get("bundle_create", {}).get("exit_code") != 0 or repo.get("bundle_verify_status") != "PASS":
            raise ValueError(f"{key}: bundle generation or verification failed")
        bundle_rel = repo.get("bundle_path")
        bundle_data = content_map.get(base + str(bundle_rel))
        if bundle_data is None or sha256_bytes(bundle_data) != repo.get("bundle_path_sha256"):
            raise ValueError(f"{key}: bundle SHA-256 does not match manifest")
        refs_rel = repo.get("local_refs_path")
        refs_data = content_map.get(base + str(refs_rel))
        if refs_data is None or sha256_bytes(refs_data) != repo.get("local_refs_sha256"):
            raise ValueError(f"{key}: local refs inventory hash mismatch")

        ref_rows = []
        for line in refs_data.decode("utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                ref_rows.append({"ref": parts[0], "object_id": parts[1], "object_type": parts[2]})
        if len(ref_rows) != repo.get("local_ref_count"):
            raise ValueError(f"{key}: local ref count mismatch")
        local_ref_map = {row["ref"]: row["object_id"] for row in ref_rows}
        for advertised in advertised_rows:
            ref = advertised.get("ref")
            oid = advertised.get("object_id")
            if not oid or ref == "HEAD" or ref.endswith("^{}"):
                continue
            if local_ref_map.get(ref) != oid:
                raise ValueError(f"{key}: advertised ref is missing/mismatched in mirror: {ref}")

        heads_rel = repo.get("bundle_heads_path")
        heads_data = content_map.get(base + str(heads_rel))
        if heads_data is None:
            raise ValueError(f"{key}: bundle head list missing")
        bundle_ref_map = {}
        for line in heads_data.decode("utf-8", errors="replace").splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                bundle_ref_map[parts[1]] = parts[0]
        for ref, oid in local_ref_map.items():
            if bundle_ref_map.get(ref) != oid:
                raise ValueError(f"{key}: ref missing/mismatched in portable bundle: {ref}")

        repo_reports.append({
            "key": key,
            "remote_url": expected_url,
            "advertised_ref_count": repo.get("advertised_ref_count"),
            "local_ref_count": repo.get("local_ref_count"),
            "reachable_commit_count": repo.get("reachable_commit_count"),
            "mirror_head_oid": repo.get("mirror_head_oid"),
            "bundle_sha256": repo.get("bundle_path_sha256"),
            "bundle_verify_status": "PASS",
            "advertised_refs_present_in_mirror": True,
            "mirror_refs_present_in_bundle": True,
            "supplemental_ref_fetches": [
                {"refspec": x.get("refspec"), "status": x.get("status")}
                for x in repo.get("supplemental_ref_fetches", [])
            ],
        })

    if manifest.get("workflow_commit_sha") != expected["workflow_sha"]:
        raise ValueError("manifest workflow SHA mismatch")
    if str(manifest.get("run_id")) != expected["run_id"] or str(manifest.get("run_attempt")) != expected["run_attempt"]:
        raise ValueError("manifest run_id/run_attempt mismatch")
    if manifest.get("workflow_ref") != expected["workflow_ref"]:
        raise ValueError("manifest workflow_ref mismatch")
    return {
        "archive_name": archive.name,
        "archive_sha256": archive_digest,
        "archive_size_bytes": archive.stat().st_size,
        "manifest_sha256": manifest_digest,
        "acquisition_status": manifest.get("acquisition_status"),
        "workflow_sha": manifest.get("workflow_commit_sha"),
        "workflow_ref": manifest.get("workflow_ref"),
        "run_id": str(manifest.get("run_id")),
        "run_attempt": str(manifest.get("run_attempt")),
        "repository_results": repo_reports,
        "manifest_file_count": len(file_inventory),
        "all_manifest_files_verified": True,
        "all_advertised_refs_present_in_mirrors": True,
        "all_mirror_refs_present_in_bundles": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--archive-checksum", required=True, type=Path)
    parser.add_argument("--slsa-json", required=True, type=Path)
    parser.add_argument("--custom-json", required=True, type=Path)
    parser.add_argument("--slsa-exit-code", required=True, type=int)
    parser.add_argument("--custom-exit-code", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    expected = {
        "repository": os.environ["GITHUB_REPOSITORY"],
        "workflow_sha": os.environ["GITHUB_SHA"],
        "workflow_ref": os.environ["GITHUB_WORKFLOW_REF"],
        "ref": os.environ["GITHUB_REF"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "workflow_path": os.environ.get("WORKFLOW_PATH", ".github/workflows/governance-raw-mirror-acquisition.yml"),
    }
    report = {
        "schema": "aura.governance-acquisition-verification-report/0.1.0",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "repository": expected["repository"],
        "workflow_sha": expected["workflow_sha"],
        "workflow_ref": expected["workflow_ref"],
        "run_id": expected["run_id"],
        "run_attempt": expected["run_attempt"],
        "historical_receipts_modified": False,
        "target_repositories_modified": False,
        "checks": {},
        "provenance_status": "UNVERIFIED",
        "acquisition_status": "UNKNOWN",
        "overall_status": "BLOCKED",
        "normative_effect": "NONE",
        "limits": [
            "Signature and trust-root verification are delegated to gh attestation verify; both invocations must exit 0.",
            "The signed acquisition archive covers advertised refs and any supplemental pull/merge-request refs the public server permitted fetching.",
            "Hidden or unreachable server-side objects, deleted refs not available through advertised refs, server reflogs, and platform audit logs are not captured by a Git clone/bundle.",
            "Verified provenance establishes acquisition artifact origin and integrity; it does not establish identity/competence of a governance authority or ratification validity.",
        ],
    }
    try:
        if args.slsa_exit_code != 0 or args.custom_exit_code != 0:
            raise ValueError(f"gh attestation verify failed: slsa={args.slsa_exit_code}, custom={args.custom_exit_code}")
        bundle = verify_archive(args.archive, args.archive_checksum, expected)
        slsa_json = json.loads(args.slsa_json.read_text(encoding="utf-8"))
        custom_json = json.loads(args.custom_json.read_text(encoding="utf-8"))
        slsa = find_verification(slsa_json, SLSA_PREDICATE)
        custom = find_verification(custom_json, CUSTOM_PREDICATE)
        if slsa is None or custom is None:
            raise ValueError("verification outputs do not include both expected predicates")
        slsa_statement = slsa.get("statement", {})
        custom_statement = custom.get("statement", {})

        def check_subject(statement: dict, label: str):
            subjects = statement.get("subject")
            if not isinstance(subjects, list) or not subjects:
                raise ValueError(f"{label} statement has no subject array")
            matches = [
                row for row in subjects
                if isinstance(row, dict) and (row.get("digest") or {}).get("sha256") == bundle["archive_sha256"]
            ]
            if len(matches) != 1:
                raise ValueError(f"{label} subject does not identify the exact acquisition archive SHA-256")
            if Path(str(matches[0].get("name", ""))).name != args.archive.name:
                raise ValueError(f"{label} subject archive name mismatch")

        check_subject(slsa_statement, "SLSA")
        check_subject(custom_statement, "custom")
        slsa_predicate = slsa_statement.get("predicate", {})
        invocation_id = (((slsa_predicate.get("runDetails") or {}).get("metadata") or {}).get("invocationId"))
        expected_invocation = f"https://github.com/{expected['repository']}/actions/runs/{expected['run_id']}/attempts/{expected['run_attempt']}"
        if invocation_id != expected_invocation:
            raise ValueError(f"SLSA invocationId mismatch: {invocation_id!r}")

        predicate = custom_statement.get("predicate", {})
        predicate_expected = {
            "predicate_schema": "aura.governance-acquisition-attestation/0.1.0",
            "repository": expected["repository"],
            "workflow_path": expected["workflow_path"],
            "workflow_ref": expected["workflow_ref"],
            "workflow_sha": expected["workflow_sha"],
            "run_id": expected["run_id"],
            "run_attempt": expected["run_attempt"],
            "subject": {"name": args.archive.name, "sha256": bundle["archive_sha256"]},
            "manifest_sha256": bundle["manifest_sha256"],
            "acquisition_status": "COMPLETE_ADVERTISED_REFS",
            "fatal_errors": [],
            "normative_effect": "NONE",
        }
        mismatches = {
            key: {"observed": predicate.get(key), "expected": value}
            for key, value in predicate_expected.items()
            if predicate.get(key) != value
        }
        if mismatches:
            raise ValueError("custom predicate binding mismatch: " + json.dumps(mismatches, sort_keys=True))
        if predicate.get("repositories") != [
            selected_repo_fields(row)
            for row in json.loads(tarfile.open(args.archive, "r:gz").extractfile("acquisition/manifest.json").read()).get("repositories", [])
        ]:
            raise ValueError("custom predicate repository snapshot does not match verified manifest")

        identity = f"https://github.com/{expected['repository']}/{expected['workflow_path']}@{expected['ref']}"
        slsa_cert = certificate_details(slsa, identity)
        custom_cert = certificate_details(custom, identity)
        report.update({
            "bundle": bundle,
            "provenance_status": "VERIFIED",
            "acquisition_status": bundle["acquisition_status"],
            "overall_status": "VERIFIED_RAW_MIRROR_ACQUISITION",
            "slsa_invocation_id": invocation_id,
            "checks": {
                "slsa_signature_trust_root_and_identity": slsa_cert,
                "custom_signature_trust_root_and_identity": custom_cert,
                "workflow_repository_ref_digest": {"status": "PASS", "expected_identity": identity, "workflow_sha": expected["workflow_sha"]},
                "exact_archive_subject_sha256": {"status": "PASS", "sha256": bundle["archive_sha256"]},
                "manifest_and_all_file_hashes": {"status": "PASS", "manifest_sha256": bundle["manifest_sha256"], "file_count": bundle["manifest_file_count"]},
                "both_public_git_mirrors": {"status": "PASS", "repositories": bundle["repository_results"]},
                "advertised_refs_and_bundles": {"status": "PASS"},
                "run_id_and_attempt_binding": {"status": "PASS", "run_id": expected["run_id"], "run_attempt": expected["run_attempt"], "slsa_invocation_id": invocation_id},
            },
        })
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["checks"]["fail_closed_verification"] = {"status": "FAIL", "detail": report["error"]}
        report["overall_status"] = "BLOCKED"
        report["provenance_status"] = "UNVERIFIED"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "overall_status": report["overall_status"],
        "provenance_status": report["provenance_status"],
        "acquisition_status": report["acquisition_status"],
        "output": str(args.output),
        "error": report.get("error"),
    }, indent=2))
    return 0 if report["overall_status"] == "VERIFIED_RAW_MIRROR_ACQUISITION" else 10


if __name__ == "__main__":
    raise SystemExit(main())
