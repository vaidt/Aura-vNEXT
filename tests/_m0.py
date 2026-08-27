"""Shared helpers for the M0 conformance, mutation, and independence suites."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _path in (REPO_ROOT, REPO_ROOT / "tools"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

# Reconstruction of an AuditEntry from a vector's recorded input lives with the
# generator, so the suite and the fixtures cannot drift into two readings of the
# same JSON. Re-exported here to keep that single definition visible to the tests.
from build_m0_fixtures import build_entry  # noqa: E402

__all__ = [
    "REPO_ROOT", "VECTORS_PATH", "REFERENCE_PACKAGE", "build_entry", "load_vectors",
    "vectors_by_name", "copy_reference_package", "read_records", "write_records",
    "refresh_manifest",
]

VECTORS_PATH = REPO_ROOT / "conformance/vectors/m0-canonical-vectors.json"
REFERENCE_PACKAGE = REPO_ROOT / "evidence/examples/aura-evidence-loan-001"


def load_vectors() -> list[dict]:
    data = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    return data["vectors"]


def vectors_by_name() -> dict[str, dict]:
    return {v["name"]: v for v in load_vectors()}


def copy_reference_package(destination: Path) -> Path:
    """Copy the reference package so a test can mutate it without touching the original."""
    target = destination / REFERENCE_PACKAGE.name
    shutil.copytree(REFERENCE_PACKAGE, target)
    return target


def read_records(package: Path) -> list[dict]:
    text = (package / "evidence/audit.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def write_records(package: Path, records: list[dict]) -> None:
    payload = "\n".join(
        json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for r in records
    ) + "\n"
    (package / "evidence/audit.jsonl").write_text(payload, encoding="utf-8")


def refresh_manifest(package: Path) -> None:
    """Recompute the manifest's file digests.

    Mutation tests call this deliberately. Without it every mutation would be caught
    by the manifest digest alone, and the suite would never exercise the canonical
    binding it exists to test. Refreshing the manifest models the stronger attacker:
    one who edits the evidence *and* repairs the obvious outer checksum.
    """
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = {
        relative: hashlib.sha256((package / relative).read_bytes()).hexdigest()
        for relative in manifest["files"]
    }
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def reseal_chain(package: Path) -> None:
    """Recompute every entry digest and relink the chain, then refresh the manifest.

    Turns an edited package back into a *legitimately sealed* one. Used to build a
    package that carries specific content before a test mutates that content, so a
    mutation test isolates the change it names instead of riding on an earlier edit.

    That this is possible at all is the honest limit of M0: the seal establishes
    integrity, not authenticity. Anyone who can rewrite the whole chain can produce a
    self-consistent package, and M0 defines no signature that would distinguish them
    from the original producer (see core/signing/README.md).
    """
    import hashlib

    from core.canonical import canonical_bytes
    from core.models import GENESIS_PREV_HASH

    records = read_records(package)
    previous = GENESIS_PREV_HASH
    for record in records:
        record["prev_hash"] = previous
        protected = {k: v for k, v in record.items() if k != "entry_hash"}
        record["entry_hash"] = hashlib.sha256(canonical_bytes(protected)).hexdigest()
        previous = record["entry_hash"]
    write_records(package, records)
    refresh_manifest(package)
