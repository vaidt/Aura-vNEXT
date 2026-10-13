#!/usr/bin/env python3
"""Build signed, supplementary metadata binding this archive to the pinned test."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import zipfile


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    archive = Path(os.environ["AURA_EVIDENCE_ARCHIVE"])
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    with zipfile.ZipFile(archive) as zf:
        names = set(zf.namelist())
        required = {"execution-receipt.json", "manifest.json", "manifest.sha256", "test-runner-exit-code.txt", "source-verification.json"}
        if not required.issubset(names):
            raise SystemExit(f"Archive missing required files: {sorted(required - names)}")
        receipt_bytes = zf.read("execution-receipt.json")
        manifest_bytes = zf.read("manifest.json")
        receipt = json.loads(receipt_bytes)
        manifest = json.loads(manifest_bytes)
        source_pin = json.loads(zf.read("source-verification.json"))
        exit_code = int(zf.read("test-runner-exit-code.txt").decode("ascii").strip())
    predicate = {
        "predicate_schema": "aura.execution-evidence-attestation/0.1.0",
        "repository": os.environ["GITHUB_REPOSITORY"],
        "workflow_path": ".github/workflows/m0-execution-provenance.yml",
        "workflow_ref": os.environ["GITHUB_WORKFLOW_REF"],
        "workflow_sha": os.environ["GITHUB_SHA"],
        "source_repository": os.environ["GITHUB_REPOSITORY"],
        "source_commit_sha_under_test": os.environ["SOURCE_SHA"],
        "source_pin_status": source_pin.get("status"),
        "source_pin_observed_commit_sha": source_pin.get("observed_commit_sha"),
        "source_protected_blob_pins": source_pin.get("protected_blobs", {}),
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "run_url": f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}/attempts/{os.environ['GITHUB_RUN_ATTEMPT']}",
        "subject": {"name": archive.name, "sha256": archive_sha},
        "manifest_sha256": sha256_bytes(manifest_bytes),
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "test_runner_exit_code": exit_code,
        "test_summary": receipt.get("test_summary", {}),
        "requirement_statuses": {
            key: value.get("execution_status") for key, value in receipt.get("requirements", {}).items()
        },
        "manifest_binding": {
            "bundle_id": manifest.get("bundle_id"),
            "run_id": manifest.get("run_id"),
            "run_attempt": manifest.get("run_attempt"),
            "source_commit_sha_under_test": manifest.get("source_commit_sha_under_test"),
            "workflow_sha": manifest.get("workflow_sha"),
        },
        "interpretation_limit": "This predicate supplements SLSA provenance; its contents are workflow assertions, not independently sourced facts. The signature and SLSA invocation metadata are verified separately.",
    }
    Path("predicate.json").write_text(json.dumps(predicate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"subject_sha256": archive_sha, "source_commit_sha_under_test": predicate["source_commit_sha_under_test"], "run_id": predicate["run_id"], "run_attempt": predicate["run_attempt"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
