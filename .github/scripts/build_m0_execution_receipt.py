#!/usr/bin/env python3
"""Create a machine-readable receipt for the pinned M0 test execution.

This receipt is self-reported. Cryptographic provenance is issued separately and
must never be represented by changing this historical receipt after signing.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import platform
import re
import subprocess
import sys

ROOT = pathlib.Path("evidence")
LOG_PATH = ROOT / "test-output.log"
RC_PATH = ROOT / "test-runner-exit-code.txt"

OUTCOME_RE = re.compile(
    r"\.\.\.\s+(ok|FAIL|ERROR|skipped(?:\s+\([^)]*\))?|expected failure|unexpected success)\s*$"
)
START_RE = re.compile(
    r"\((?:[A-Za-z_][A-Za-z0-9_]*\.)*(?P<class>[A-Za-z_][A-Za-z0-9_]*)"
    r"\.(?P<method>test_[A-Za-z0-9_]+)\)(?:\s+\.\.\.\s+"
    r"(?P<inline>ok|FAIL|ERROR|skipped(?:\s+\([^)]*\))?|expected failure|unexpected success))?\s*$"
)

REQUIREMENTS = {
    "M0-PKG-BOUNDARY-001": [
        "ParentTraversalTest.test_parent_traversal_is_invalid",
        "ParentTraversalTest.test_deep_parent_traversal_is_invalid",
        "ParentTraversalTest.test_nested_traversal_is_invalid",
        "ParentTraversalTest.test_traversal_that_lands_back_inside_is_still_invalid",
    ],
    "M0-PKG-BOUNDARY-002": [
        "AbsolutePathTest.test_absolute_path_is_invalid",
        "AbsolutePathTest.test_absolute_system_path_is_invalid",
        "AbsolutePathTest.test_root_itself_is_invalid",
    ],
    "M0-PKG-BOUNDARY-003": [
        "ParentTraversalTest.test_non_canonical_spellings_are_invalid",
        "AbsolutePathTest.test_backslash_separator_is_invalid",
        "AbsolutePathTest.test_empty_and_non_string_paths_are_invalid",
    ],
    "M0-PKG-BOUNDARY-004": [
        "SymlinkEscapeTest.test_symlink_to_a_file_outside_the_package_is_invalid",
        "SymlinkEscapeTest.test_symlink_to_a_directory_outside_the_package_is_invalid",
    ],
    "M0-PKG-BOUNDARY-005": [
        "SymlinkEscapeTest.test_a_symlink_staying_inside_the_package_is_not_an_escape",
        "LegitimateInternalPathTest.test_an_additional_declared_file_inside_the_package_verifies",
        "LegitimateInternalPathTest.test_the_reference_package_still_verifies",
        "LegitimateInternalPathTest.test_a_package_reached_through_a_symlinked_root_verifies",
    ],
}
EXPECTED_BLOBS = {
    "tests/conformance/test_package_boundary.py": "3ce5b030326661eb66cbd6016a9ad4fe1812db6e",
    "app/verifier/__init__.py": "0091a7aca79c1f5aef1358399ab393da98c9a1b2",
    "docs/contract/M0-EVIDENCE-CONTRACT.md": "daa1201232ebe0a75082ac71806042d59ca46b62",
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        LOG_PATH.write_text("test runner did not execute; output unavailable\n", encoding="utf-8")
    if not RC_PATH.exists():
        RC_PATH.write_text("125\n", encoding="ascii")

    log = LOG_PATH.read_text(encoding="utf-8", errors="replace")
    try:
        rc = int(RC_PATH.read_text(encoding="ascii").strip())
    except (ValueError, OSError):
        rc = 125
    source_sha = os.environ.get("SOURCE_SHA", "")
    observed_source = None
    try:
        observed_source = subprocess.check_output(
            ["git", "-C", "source", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        pass

    results: dict[str, str] = {}
    lines = log.splitlines()
    for index, line in enumerate(lines):
        match = START_RE.search(line.rstrip())
        if not match:
            continue
        symbol = f"{match.group('class')}.{match.group('method')}"
        outcome = match.group("inline")
        if outcome is None and index + 1 < len(lines):
            following = OUTCOME_RE.search(lines[index + 1].strip())
            if following:
                outcome = following.group(1)
        if outcome is not None:
            results[symbol] = outcome.split(" ", 1)[0]

    mapped = {}
    for requirement, symbols in REQUIREMENTS.items():
        observed = {symbol: results.get(symbol, "NOT_OBSERVED") for symbol in symbols}
        if any(value in {"FAIL", "ERROR", "unexpected"} for value in observed.values()):
            status, matched = "FAIL", False
        elif rc != 0:
            status, matched = "BLOCKED", None
        elif all(value == "ok" for value in observed.values()):
            status, matched = "TESTED", True
        else:
            status, matched = "BLOCKED", None
        mapped[requirement] = {
            "execution_status": status,
            "matched_expected": matched,
            "tests": observed,
        }

    summary = re.search(r"Ran (\d+) tests? in ([0-9.]+)s", log)
    now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    receipt = {
        "receipt_schema": "aura.execution-receipt/0.1.0",
        "execution_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "run_url": (
            f"https://github.com/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/"
            f"{os.environ.get('GITHUB_RUN_ID')}/attempts/{os.environ.get('GITHUB_RUN_ATTEMPT')}"
        ),
        "repository": os.environ.get("GITHUB_REPOSITORY"),
        "provenance_status": "SELF_REPORTED_UNSIGNED",
        "provenance_attestation": {
            "issuer": "GitHub Actions execution receipt; signed provenance handled separately",
            "signature_scheme": None,
            "signature_or_attestation_reference": None,
            "validation_status": "NOT_RUN",
        },
        "runner_definition_commit_sha": os.environ.get("GITHUB_SHA"),
        "runner_definition_ref": os.environ.get("GITHUB_REF"),
        "runner_workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "workflow_path": ".github/workflows/m0-execution-provenance.yml",
        "source_commit_sha_expected": source_sha,
        "source_commit_sha_observed": observed_source,
        "source_blobs_expected": EXPECTED_BLOBS,
        "command": "python3 -m unittest discover -s tests/conformance -p test_package_boundary.py -v",
        "environment_overrides": {"PYTHONPATH": "tests"},
        "started_at": os.environ.get("AURA_TEST_STARTED_AT"),
        "completed_at": now,
        "environment": {
            "runner_os": os.environ.get("RUNNER_OS"),
            "runner_arch": os.environ.get("RUNNER_ARCH"),
            "image_os": platform.platform(),
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
        },
        "test_runner_exit_code": rc,
        "test_summary": {
            "tests_run": int(summary.group(1)) if summary else None,
            "duration_seconds": float(summary.group(2)) if summary else None,
        },
        "observed_test_results": results,
        "requirements": mapped,
        "output_artifact": "test-output.log",
        "output_sha256": sha256(LOG_PATH),
        "independent_verification_status": "NOT_RUN",
        "limits": [
            "Receipt is self-reported and unsigned; cryptographic provenance is issued separately.",
            "The tested source is the exact pinned checkout; workflow definition is a separate commit.",
            "TESTED is the maximum requirement status; VERIFIED provenance does not imply CONFORMANT.",
        ],
    }
    receipt_path = ROOT / "execution-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "execution-receipt.sha256").write_text(
        f"{sha256(receipt_path)}  execution-receipt.json\n", encoding="ascii"
    )
    print(json.dumps({
        "run_id": receipt["execution_id"],
        "run_attempt": receipt["run_attempt"],
        "source_expected": source_sha,
        "source_observed": observed_source,
        "test_runner_exit_code": rc,
        "tests_run": receipt["test_summary"]["tests_run"],
        "requirements": {key: value["execution_status"] for key, value in mapped.items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
