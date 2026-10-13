#!/usr/bin/env python3
"""Create a final M0 evidence ZIP and a non-circular manifest/checksum set."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import zipfile

SOURCE = Path("evidence")
DIST = Path("dist")
PAYLOAD_FILES = [
    "execution-receipt.json",
    "execution-receipt.sha256",
    "test-output.log",
    "test-runner-exit-code.txt",
    "source-verification.json",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def main() -> int:
    DIST.mkdir(parents=True, exist_ok=True)
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    repository = os.environ["GITHUB_REPOSITORY"]
    source_sha = os.environ.get("SOURCE_SHA", "")
    workflow_sha = os.environ.get("GITHUB_SHA", "")
    bundle_id = f"{repository}:{run_id}:{attempt}"
    payload = {}
    for name in PAYLOAD_FILES:
        path = SOURCE / name
        if not path.is_file():
            path.write_text("unavailable: prior evidence step did not produce this file\n", encoding="utf-8")
        payload[name] = path.read_bytes()

    manifest = {
        "manifest_schema": "aura.execution-evidence-manifest/0.1.0",
        "bundle_id": bundle_id,
        "repository": repository,
        "workflow_path": ".github/workflows/m0-execution-provenance.yml",
        "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF"),
        "workflow_sha": workflow_sha,
        "source_repository": repository,
        "source_commit_sha_under_test": source_sha,
        "run_id": run_id,
        "run_attempt": attempt,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "files": {name: {"size_bytes": len(data), "sha256": sha256_bytes(data)} for name, data in payload.items()},
        "manifest_self_reference": "manifest.json is excluded from files to avoid a self-referential digest; manifest.sha256 records its digest.",
        "cryptographic_attestation": "issued separately for the final ZIP subject; it is not embedded to avoid circularity",
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest_sha = sha256_bytes(manifest_bytes)
    checksum_bytes = f"{manifest_sha}  manifest.json\n".encode("ascii")

    inner_files = dict(payload)
    inner_files["manifest.json"] = manifest_bytes
    inner_files["manifest.sha256"] = checksum_bytes
    archive = DIST / f"aura-m0-package-boundary-evidence-{run_id}-attempt-{attempt}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(inner_files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            zf.writestr(info, inner_files[name])

    archive_sha = sha256_file(archive)
    (DIST / (archive.name + ".sha256")).write_text(f"{archive_sha}  {archive.name}\n", encoding="ascii")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as out:
            out.write("## M0 evidence bundle\n\n")
            out.write(f"- Bundle: {archive.name}\n- SHA-256: {archive_sha}\n")
            out.write(f"- Manifest SHA-256: {manifest_sha}\n- Source under test: {source_sha}\n")
            out.write(f"- Run / attempt: {run_id} / {attempt}\n")
    print(json.dumps({
        "archive": str(archive),
        "archive_sha256": archive_sha,
        "manifest_sha256": manifest_sha,
        "receipt_sha256": sha256_bytes(payload["execution-receipt.json"]),
        "source_commit_sha_under_test": source_sha,
        "run_id": run_id,
        "run_attempt": attempt,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
