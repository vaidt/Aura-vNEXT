#!/usr/bin/env python3
"""Record and verify the exact pinned source commit and protected blob identities."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import sys

EXPECTED_COMMIT = "bdec831c165b3a5465bc25f325ed801558cbf81a"
EXPECTED_BLOBS = {
    "tests/conformance/test_package_boundary.py": "3ce5b030326661eb66cbd6016a9ad4fe1812db6e",
    "app/verifier/__init__.py": "0091a7aca79c1f5aef1358399ab393da98c9a1b2",
    "docs/contract/M0-EVIDENCE-CONTRACT.md": "daa1201232ebe0a75082ac71806042d59ca46b62",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True, stderr=subprocess.STDOUT).strip()


def main() -> int:
    repo = Path("source")
    result = {
        "source_pin_schema": "aura.m0-source-pin-verification/0.1.0",
        "expected_commit_sha": EXPECTED_COMMIT,
        "observed_commit_sha": None,
        "protected_blobs": {},
        "status": "BLOCKED",
        "errors": [],
    }
    try:
        result["observed_commit_sha"] = git(repo, "rev-parse", "HEAD")
        if result["observed_commit_sha"] != EXPECTED_COMMIT:
            result["errors"].append({"kind": "commit_mismatch", "expected": EXPECTED_COMMIT, "observed": result["observed_commit_sha"]})
        for path, expected in EXPECTED_BLOBS.items():
            try:
                observed = git(repo, "rev-parse", f"HEAD:{path}")
            except subprocess.CalledProcessError as exc:
                observed = None
                result["errors"].append({"kind": "blob_lookup_failed", "path": path, "detail": exc.output})
            result["protected_blobs"][path] = {"expected": expected, "observed": observed, "matches": observed == expected}
            if observed != expected:
                result["errors"].append({"kind": "blob_mismatch", "path": path, "expected": expected, "observed": observed})
        if not result["errors"]:
            result["status"] = "PASS"
    except (OSError, subprocess.CalledProcessError) as exc:
        result["errors"].append({"kind": "source_checkout_unavailable", "detail": str(exc)})
    output = Path("evidence/source-verification.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 20


if __name__ == "__main__":
    raise SystemExit(main())
