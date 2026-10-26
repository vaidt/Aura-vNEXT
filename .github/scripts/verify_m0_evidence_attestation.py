#!/usr/bin/env python3
"""Fail-closed independent verifier for M0 ZIP attestations.

Cryptographic verification is performed by the separately invoked gh attestation
verify CLI with repository, signer-workflow, source-ref and source-digest pins.
This script independently validates the CLI result JSON, certificate identity data,
SLSA invocation ID, exact ZIP subject digest, bundle manifest and signed custom
predicate. It never edits execution-receipt.json.
"""

from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import zipfile

SLSA_PREDICATE = "https://slsa.dev/provenance/v1"
CUSTOM_PREDICATE = (
    "https://github.com/vaidt/Aura-vNEXT/attestations/aura-execution-evidence/v1"
)
REQUIRED_PAYLOAD = {
    "execution-receipt.json",
    "execution-receipt.sha256",
    "test-output.log",
    "test-runner-exit-code.txt",
    "source-verification.json",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


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
        if not isinstance(vr, dict):
            continue
        statement = vr.get("statement")
        if (
            isinstance(statement, dict)
            and statement.get("predicateType") == predicate_type
        ):
            return vr
    return _find_statement(value, predicate_type)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from strings(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from strings(nested)


def certificate_details(verification: dict, expected_workflow_identity: str) -> dict:
    cert = _certificate_object(verification)

    cert_strings = list(strings(cert))
    issuer_ok = any(
        value == "https://token.actions.githubusercontent.com" for value in cert_strings
    )
    san_candidates = _certificate_sans(cert, cert_strings)

    san_match = any(expected_workflow_identity in value for value in san_candidates)
    timestamp_count = _verified_timestamp_count(verification)

    if not issuer_ok:
        raise ValueError(
            "certificate JSON does not expose the expected GitHub Actions OIDC issuer"
        )
    if not san_candidates or not san_match:
        raise ValueError(
            "certificate SAN does not bind the expected repository/workflow/ref identity"
        )
    if timestamp_count < 1:
        raise ValueError("no verified transparency timestamp was returned by the CLI")
    return {
        "issuer_match": True,
        "certificate_identity": next(
            (value for value in san_candidates if expected_workflow_identity in value),
            None,
        ),
        "verified_timestamp_count": timestamp_count,
        "certificate_fields_observed": sorted(cert.keys()),
    }


def validate_archive(archive: Path, sidecar: Path | None, expected: dict) -> dict:
    archive_digest = sha256_file(archive)
    if sidecar and sidecar.is_file():
        match = re.fullmatch(
            r"([0-9a-f]{64})\s+\*?([^\r\n]+)\s*\n?", sidecar.read_text(encoding="ascii")
        )
        if not match or match.group(1) != archive_digest:
            raise ValueError("outer ZIP SHA-256 sidecar does not match archive bytes")
    contents, names = _read_zip_payload(archive)

    manifest, manifest_digest = _verify_manifest(contents)

    receipt_bytes = contents["execution-receipt.json"]
    receipt = json.loads(receipt_bytes)
    source_pin = json.loads(contents["source-verification.json"])
    _verify_source_pins(source_pin, expected)

    _verify_receipt_checksum(contents, receipt_bytes)

    exit_code = int(contents["test-runner-exit-code.txt"].decode("ascii").strip())

    comparisons = _verify_receipt_bindings(manifest, receipt, expected, exit_code)

    requirement_statuses, execution_status = _execution_result(receipt, exit_code)

    return {
        "archive_sha256": archive_digest,
        "archive_name": archive.name,
        "archive_entry_names": sorted(names),
        "manifest_sha256": manifest_digest,
        "receipt_sha256": sha256_bytes(receipt_bytes),
        "source_commit_sha_under_test": expected["source_sha"],
        "workflow_sha": expected["workflow_sha"],
        "run_id": expected["run_id"],
        "run_attempt": expected["run_attempt"],
        "test_runner_exit_code": exit_code,
        "requirement_statuses": requirement_statuses,
        "execution_status": execution_status,
        "manifest_and_receipt_binding_checks": {key: True for key in comparisons},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--archive-checksum", type=Path)
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
        "source_sha": os.environ["SOURCE_SHA"],
        "run_id": os.environ["GITHUB_RUN_ID"],
        "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"],
        "workflow_path": ".github/workflows/m0-execution-provenance.yml",
    }
    report = {
        "report_schema": "aura.execution-provenance-verification-report/0.1.0",
        "created_at_utc": dt.datetime.now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "repository": expected["repository"],
        "workflow_ref": expected["workflow_ref"],
        "workflow_sha": expected["workflow_sha"],
        "source_commit_sha_under_test": expected["source_sha"],
        "run_id": expected["run_id"],
        "run_attempt": expected["run_attempt"],
        "historical_receipt_modified": False,
        "checks": {},
        "provenance_status": "UNVERIFIED",
        "execution_status": "UNKNOWN",
        "overall_status": "BLOCKED",
        "limits": [
            "Cryptographic signature, trust-root and signer workflow validation are delegated to GitHub CLI gh attestation verify; both invocations must exit 0.",
            "SLSA invocation metadata authenticates run_id/run_attempt. The supplementary signed predicate binds the pinned secondary checkout under test.",
            "A verified execution-evidence archive does not establish protocol conformance or normative effect.",
            "The custom predicate is workflow-authored metadata; it is checked against the receipt, manifest and explicitly pinned expected values.",
        ],
    }
    try:
        if args.slsa_exit_code != 0 or args.custom_exit_code != 0:
            raise ValueError(
                f"gh attestation verify failed: slsa_exit={args.slsa_exit_code}, custom_exit={args.custom_exit_code}"
            )
        bundle_info = validate_archive(args.archive, args.archive_checksum, expected)
        slsa, custom, slsa_statement, custom_statement = _load_verified_statements(
            args, bundle_info
        )

        slsa_predicate = slsa_statement.get("predicate", {})
        invocation_id = (
            (slsa_predicate.get("runDetails") or {}).get("metadata") or {}
        ).get("invocationId")
        expected_invocation = f"https://github.com/{expected['repository']}/actions/runs/{expected['run_id']}/attempts/{expected['run_attempt']}"
        if invocation_id != expected_invocation:
            raise ValueError(
                f"SLSA invocationId mismatch: observed={invocation_id!r}, expected={expected_invocation!r}"
            )

        _verify_custom_predicate(custom_statement, expected, args, bundle_info)

        identity = f"https://github.com/{expected['repository']}/{expected['workflow_path']}@{expected['ref']}"
        slsa_cert = certificate_details(slsa, identity)
        custom_cert = certificate_details(custom, identity)
        report["bundle"] = bundle_info
        report["checks"] = {
            "slsa_signature_and_trust_root": {
                "status": "PASS",
                "cli_exit_code": args.slsa_exit_code,
                **slsa_cert,
            },
            "custom_signature_and_trust_root": {
                "status": "PASS",
                "cli_exit_code": args.custom_exit_code,
                **custom_cert,
            },
            "trusted_signer_repository_and_workflow": {
                "status": "PASS",
                "enforced_by": "gh attestation verify --repo and --signer-workflow",
                "expected_identity": identity,
            },
            "workflow_source_digest_and_ref": {
                "status": "PASS",
                "enforced_by": "gh attestation verify --source-digest and --source-ref",
                "source_digest": expected["workflow_sha"],
                "source_ref": expected["ref"],
            },
            "exact_subject_zip_sha256": {
                "status": "PASS",
                "sha256": bundle_info["archive_sha256"],
            },
            "source_commit_under_test_binding": {
                "status": "PASS",
                "source_repository": expected["repository"],
                "source_commit_sha": expected["source_sha"],
            },
            "run_id_and_attempt_binding": {
                "status": "PASS",
                "run_id": expected["run_id"],
                "run_attempt": expected["run_attempt"],
                "slsa_invocation_id": invocation_id,
            },
            "manifest_receipt_log_exit_code_integrity": {
                "status": "PASS",
                "manifest_sha256": bundle_info["manifest_sha256"],
                "receipt_sha256": bundle_info["receipt_sha256"],
            },
            "pinned_source_commit_and_protected_blobs": {
                "status": "PASS",
                "source_commit_sha": expected["source_sha"],
                "protected_blob_count": 3,
            },
        }
        report["provenance_status"] = "VERIFIED"
        report["execution_status"] = bundle_info["execution_status"]
        report["overall_status"] = (
            "VERIFIED_EXECUTION_EVIDENCE"
            if bundle_info["execution_status"] == "PASS"
            else "VERIFIED_PROVENANCE_EXECUTION_FAILED_OR_BLOCKED"
        )
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["checks"]["fail_closed_verification"] = {
            "status": "FAIL",
            "detail": report["error"],
        }
        report["provenance_status"] = "UNVERIFIED"
        report["overall_status"] = "BLOCKED"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "overall_status": report["overall_status"],
                "provenance_status": report["provenance_status"],
                "execution_status": report["execution_status"],
                "output": str(args.output),
                "error": report.get("error"),
            },
            indent=2,
        )
    )
    return 0 if report["overall_status"] == "VERIFIED_EXECUTION_EVIDENCE" else 10


def _read_zip_payload(archive):
    with zipfile.ZipFile(archive, "r") as zf:
        infos = zf.infolist()
        names = [item.filename for item in infos]
        if len(names) != len(set(names)):
            raise ValueError("archive contains duplicate entry names")
        for info in infos:
            _validate_zip_member(info)

        expected_names = REQUIRED_PAYLOAD | {"manifest.json", "manifest.sha256"}
        if set(names) != expected_names:
            raise ValueError(
                f"archive entry set mismatch; observed={sorted(names)}, expected={sorted(expected_names)}"
            )
        contents = {name: zf.read(name) for name in names}
    return contents, names


def _verify_manifest(contents):
    manifest_bytes = contents["manifest.json"]
    manifest_digest = sha256_bytes(manifest_bytes)
    sidecar_match = re.fullmatch(
        r"([0-9a-f]{64})\s+manifest\.json\s*\n?",
        contents["manifest.sha256"].decode("ascii"),
    )
    if not sidecar_match or sidecar_match.group(1) != manifest_digest:
        raise ValueError("manifest.sha256 does not match manifest.json")
    manifest = json.loads(manifest_bytes)
    if manifest.get("manifest_schema") != "aura.execution-evidence-manifest/0.1.0":
        raise ValueError("unsupported or missing manifest schema")
    files = manifest.get("files")
    if not isinstance(files, dict) or set(files) != REQUIRED_PAYLOAD:
        raise ValueError(
            "manifest file inventory does not exactly cover the required payload"
        )
    for name, spec in files.items():
        data = contents[name]
        if spec.get("sha256") != sha256_bytes(data) or spec.get("size_bytes") != len(
            data
        ):
            raise ValueError(f"manifest hash/size mismatch for {name}")
    return manifest, manifest_digest


def _verify_source_pins(source_pin, expected):
    if (
        source_pin.get("status") != "PASS"
        or source_pin.get("observed_commit_sha") != expected["source_sha"]
    ):
        raise ValueError(
            "source-verification.json does not establish the pinned source commit"
        )
    for path, expected_blob in {
        "tests/conformance/test_package_boundary.py": "3ce5b030326661eb66cbd6016a9ad4fe1812db6e",
        "app/verifier/__init__.py": "0091a7aca79c1f5aef1358399ab393da98c9a1b2",
        "docs/contract/M0-EVIDENCE-CONTRACT.md": "daa1201232ebe0a75082ac71806042d59ca46b62",
    }.items():
        row = source_pin.get("protected_blobs", {}).get(path, {})
        if (
            row.get("expected") != expected_blob
            or row.get("observed") != expected_blob
            or row.get("matches") is not True
        ):
            raise ValueError(f"protected source blob mismatch for {path}")


def _verify_receipt_checksum(contents, receipt_bytes):
    receipt_checksum = re.fullmatch(
        r"([0-9a-f]{64})\s+execution-receipt\.json\s*\n?",
        contents["execution-receipt.sha256"].decode("ascii"),
    )
    if not receipt_checksum or receipt_checksum.group(1) != sha256_bytes(receipt_bytes):
        raise ValueError("execution-receipt.sha256 mismatch")


def _verify_receipt_bindings(manifest, receipt, expected, exit_code):
    comparisons = {
        "manifest.repository": (manifest.get("repository"), expected["repository"]),
        "manifest.workflow_sha": (
            manifest.get("workflow_sha"),
            expected["workflow_sha"],
        ),
        "manifest.source_commit_sha_under_test": (
            manifest.get("source_commit_sha_under_test"),
            expected["source_sha"],
        ),
        "manifest.run_id": (str(manifest.get("run_id")), expected["run_id"]),
        "manifest.run_attempt": (
            str(manifest.get("run_attempt")),
            expected["run_attempt"],
        ),
        "receipt.repository": (receipt.get("repository"), expected["repository"]),
        "receipt.runner_definition_commit_sha": (
            receipt.get("runner_definition_commit_sha"),
            expected["workflow_sha"],
        ),
        "receipt.source_commit_sha_expected": (
            receipt.get("source_commit_sha_expected"),
            expected["source_sha"],
        ),
        "receipt.source_commit_sha_observed": (
            receipt.get("source_commit_sha_observed"),
            expected["source_sha"],
        ),
        "receipt.execution_id": (str(receipt.get("execution_id")), expected["run_id"]),
        "receipt.run_attempt": (
            str(receipt.get("run_attempt")),
            expected["run_attempt"],
        ),
        "receipt.test_runner_exit_code": (
            receipt.get("test_runner_exit_code"),
            exit_code,
        ),
    }
    mismatch = {
        key: {"observed": actual, "expected": wanted}
        for key, (actual, wanted) in comparisons.items()
        if actual != wanted
    }
    if mismatch:
        raise ValueError(
            "receipt/manifest expected-value mismatch: "
            + json.dumps(mismatch, sort_keys=True)
        )
    return comparisons


def _certificate_object(verification):
    signature = verification.get("signature")
    if not isinstance(signature, dict):
        raise ValueError("verified CLI result lacks signature object")
    cert = signature.get("certificate")
    if not isinstance(cert, dict) or not cert:
        raise ValueError("verified CLI result lacks signing certificate details")
    return cert


def _certificate_sans(cert, cert_strings):
    san_candidates = []
    for key in (
        "san",
        "subjectAlternativeName",
        "subject_alternative_name",
        "subjectAltName",
    ):
        if key in cert:
            san_candidates.extend(list(strings(cert[key])))
    if not san_candidates:
        san_candidates = [
            value
            for value in cert_strings
            if "github.com/vaidt/Aura-vNEXT/.github/workflows/" in value
        ]
    return san_candidates


def _verified_timestamp_count(verification):
    timestamps = verification.get("verifiedTimestamps")
    if timestamps is None:
        timestamps = verification.get("verified_timestamps")
    timestamp_count = len(timestamps) if isinstance(timestamps, list) else 0
    return timestamp_count


def _find_statement(value, predicate_type):
    for item in walk(value):
        if (
            isinstance(item, dict)
            and item.get("predicateType") == predicate_type
            and "subject" in item
            and "predicate" in item
        ):
            return {"statement": item}
    return None


def _load_verified_statements(args, bundle_info):
    slsa_json = json.loads(args.slsa_json.read_text(encoding="utf-8"))
    custom_json = json.loads(args.custom_json.read_text(encoding="utf-8"))
    slsa = find_verification(slsa_json, SLSA_PREDICATE)
    custom = find_verification(custom_json, CUSTOM_PREDICATE)
    if slsa is None or custom is None:
        raise ValueError(
            "CLI output lacks verified SLSA and/or custom predicate statement"
        )
    slsa_statement = slsa.get("statement", {})
    custom_statement = custom.get("statement", {})

    def check_subject(statement: dict, label: str):
        subjects = statement.get("subject")
        if not isinstance(subjects, list) or not subjects:
            raise ValueError(f"{label}: statement has no subject array")
        matching = [
            s
            for s in subjects
            if isinstance(s, dict)
            and (s.get("digest") or {}).get("sha256") == bundle_info["archive_sha256"]
        ]
        if len(matching) != 1:
            raise ValueError(
                f"{label}: statement subject does not bind exactly the observed ZIP SHA-256"
            )
        if Path(str(matching[0].get("name", ""))).name != args.archive.name:
            raise ValueError(
                f"{label}: subject name does not match the evidence ZIP basename"
            )

    check_subject(slsa_statement, "SLSA")
    check_subject(custom_statement, "custom predicate")
    return slsa, custom, slsa_statement, custom_statement


def _execution_result(receipt, exit_code):
    requirement_statuses = {
        key: value.get("execution_status")
        for key, value in receipt.get("requirements", {}).items()
    }
    execution_status = (
        "PASS"
        if exit_code == 0
        and len(requirement_statuses) == 5
        and all(value == "TESTED" for value in requirement_statuses.values())
        else "FAIL_OR_BLOCKED"
    )
    return requirement_statuses, execution_status


def _validate_zip_member(info):
    name = info.filename
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or not name
        or name.startswith("/")
    ):
        raise ValueError(f"unsafe archive path: {name!r}")
    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
        raise ValueError(f"symlink entry not allowed: {name}")


def _verify_custom_predicate(custom_statement, expected, args, bundle_info):
    custom_predicate = custom_statement.get("predicate", {})
    predicate_expected = {
        "repository": expected["repository"],
        "workflow_path": expected["workflow_path"],
        "workflow_ref": expected["workflow_ref"],
        "workflow_sha": expected["workflow_sha"],
        "source_repository": expected["repository"],
        "source_commit_sha_under_test": expected["source_sha"],
        "run_id": expected["run_id"],
        "run_attempt": expected["run_attempt"],
        "subject": {"name": args.archive.name, "sha256": bundle_info["archive_sha256"]},
        "manifest_sha256": bundle_info["manifest_sha256"],
        "receipt_sha256": bundle_info["receipt_sha256"],
        "test_runner_exit_code": bundle_info["test_runner_exit_code"],
        "source_pin_status": "PASS",
        "source_pin_observed_commit_sha": expected["source_sha"],
    }
    custom_mismatches = {
        key: {"observed": custom_predicate.get(key), "expected": value}
        for key, value in predicate_expected.items()
        if custom_predicate.get(key) != value
    }
    expected_blob_pins = {
        "tests/conformance/test_package_boundary.py": {
            "expected": "3ce5b030326661eb66cbd6016a9ad4fe1812db6e",
            "observed": "3ce5b030326661eb66cbd6016a9ad4fe1812db6e",
            "matches": True,
        },
        "app/verifier/__init__.py": {
            "expected": "0091a7aca79c1f5aef1358399ab393da98c9a1b2",
            "observed": "0091a7aca79c1f5aef1358399ab393da98c9a1b2",
            "matches": True,
        },
        "docs/contract/M0-EVIDENCE-CONTRACT.md": {
            "expected": "daa1201232ebe0a75082ac71806042d59ca46b62",
            "observed": "daa1201232ebe0a75082ac71806042d59ca46b62",
            "matches": True,
        },
    }
    if custom_mismatches:
        raise ValueError(
            "custom attestation predicate binding mismatch: "
            + json.dumps(custom_mismatches, sort_keys=True)
        )
    if custom_predicate.get("source_protected_blob_pins") != expected_blob_pins:
        raise ValueError(
            "custom attestation predicate protected-blob bindings do not match the hard-coded pins"
        )
    expected_manifest_binding = {
        "bundle_id": f"{expected['repository']}:{expected['run_id']}:{expected['run_attempt']}",
        "run_id": expected["run_id"],
        "run_attempt": expected["run_attempt"],
        "source_commit_sha_under_test": expected["source_sha"],
        "workflow_sha": expected["workflow_sha"],
    }
    if custom_predicate.get("manifest_binding") != expected_manifest_binding:
        raise ValueError("custom attestation manifest binding mismatch")


if __name__ == "__main__":
    raise SystemExit(main())
