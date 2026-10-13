#!/usr/bin/env python3
"""Create a signed-predicate payload for the exact governance acquisition tarball."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tarfile


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
            {"refspec": x.get("refspec"), "status": x.get("status")}
            for x in repo.get("supplemental_ref_fetches", [])
        ],
    }


def main() -> int:
    archive = Path(os.environ["AURA_ACQUISITION_ARCHIVE"])
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with tarfile.open(archive, "r:gz") as tf:
        mf = tf.extractfile("acquisition/manifest.json")
        checksum = tf.extractfile("acquisition/manifest.sha256")
        if mf is None or checksum is None:
            raise SystemExit("Acquisition archive has no embedded manifest/checksum.")
        manifest_bytes = mf.read()
        checksum_text = checksum.read().decode("ascii")
    manifest_sha = sha256_bytes(manifest_bytes)
    expected_checksum = f"{manifest_sha}  manifest.json"
    if checksum_text.strip() != expected_checksum:
        raise SystemExit("Embedded manifest checksum mismatch.")
    manifest = json.loads(manifest_bytes)
    predicate = {
        "predicate_schema": "aura.governance-acquisition-attestation/0.1.0",
        "repository": os.environ["GITHUB_REPOSITORY"],
        "workflow_path": os.environ.get("WORKFLOW_PATH", ".github/workflows/governance-raw-mirror-acquisition.yml"),
        "workflow_ref": os.environ["GITHUB_WORKFLOW_REF"],
        "workflow_sha": os.environ["GITHUB_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "run_url": f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}/attempts/{os.environ['GITHUB_RUN_ATTEMPT']}",
        "subject": {"name": archive.name, "sha256": digest},
        "manifest_sha256": manifest_sha,
        "acquisition_status": manifest.get("acquisition_status"),
        "repositories": [selected_repo_fields(r) for r in manifest.get("repositories", [])],
        "fatal_errors": manifest.get("fatal_errors", []),
        "scope": "Advertised Git refs plus any recorded, fetchable host-specific pull/merge-request refs. Not server reflogs, hidden unreachable objects, or hosting audit logs.",
        "normative_effect": "NONE",
        "interpretation_limit": "The signed predicate authenticates the workflow's acquisition statement; it does not prove governance authority, canonicality, ratification, or normative effect.",
    }
    Path("predicate.json").write_text(json.dumps(predicate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"archive": archive.name, "archive_sha256": digest, "manifest_sha256": manifest_sha, "acquisition_status": predicate["acquisition_status"], "run_id": predicate["run_id"], "run_attempt": predicate["run_attempt"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
