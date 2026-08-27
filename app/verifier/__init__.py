"""Independent verification of an M0 Evidence Package (ADR-0006).

The verifier reads a package directory and nothing else. It does not import the
producer, open a database, reach the network, execute a policy engine, or consult any
state outside the directory it is given. That constraint is the product claim; the
`tests/test_independence.py` suite exists to keep it true.

Three externally visible results, which are never collapsed into each other:

    VERIFIED  structurally valid, and every required integrity check succeeded
    TAMPERED  recognisable as an M0 package, but protected evidence fails integrity
    INVALID   cannot be interpreted as an M0 Evidence Package at all

VERIFIED establishes integrity, not authenticity: M0 defines no signature scheme
(see core/signing/README.md). Both TAMPERED and INVALID are refusals; only VERIFIED
is acceptance.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from core import M0_AUDIT_SCHEMA, M0_PACKAGE_PROFILE
from core.canonical import CanonicalisationError
from core.chain import ChainError, verify_chain
from core.policy import policy_hash

__all__ = ["VERIFIED", "TAMPERED", "INVALID", "VerificationResult", "verify_package"]

VERIFIED = "VERIFIED"
TAMPERED = "TAMPERED"
INVALID = "INVALID"

REQUIRED_FILES = ("evidence/audit.jsonl", "evidence/policy.json", "evidence/genesis.json")


@dataclass(frozen=True)
class VerificationResult:
    status: str
    reasons: tuple[str, ...] = ()
    package_id: str | None = None
    entries: int = 0

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "package_id": self.package_id,
            "entries": self.entries,
            "reasons": list(self.reasons),
        }


class _Invalid(Exception):
    """Raised internally when the package cannot be interpreted."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _read_json(path: Path, label: str):
    if not path.is_file():
        raise _Invalid(f"{label}: required file is missing")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _Invalid(f"{label}: not readable as UTF-8 ({exc})") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise _Invalid(f"{label}: malformed JSON ({exc.msg} at line {exc.lineno})") from exc


def _read_jsonl(path: Path, label: str) -> list:
    if not path.is_file():
        raise _Invalid(f"{label}: required file is missing")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _Invalid(f"{label}: not readable as UTF-8 ({exc})") from exc

    records = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _Invalid(f"{label}: malformed JSON on line {number} ({exc.msg})") from exc
        if not isinstance(record, dict):
            raise _Invalid(f"{label}: line {number} is not a JSON object")
        records.append(record)

    if not records:
        raise _Invalid(f"{label}: contains no audit records")
    return records


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_structure(root: Path) -> tuple[dict, list, dict, dict]:
    """Establish that this is an M0 package. Every failure here means INVALID."""
    if not root.is_dir():
        raise _Invalid(f"{root}: not a directory")

    manifest = _read_json(root / "manifest.json", "manifest.json")
    if not isinstance(manifest, dict):
        raise _Invalid("manifest.json: top level is not a JSON object")

    profile = manifest.get("profile")
    if profile != M0_PACKAGE_PROFILE:
        raise _Invalid(
            f"manifest.json: unsupported profile {profile!r} "
            f"(this verifier implements {M0_PACKAGE_PROFILE})"
        )

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise _Invalid("manifest.json: 'files' is missing or is not an object")

    for required in REQUIRED_FILES:
        if required not in files:
            raise _Invalid(f"manifest.json: does not declare required file {required}")
        if not (root / required).is_file():
            raise _Invalid(f"{required}: declared in the manifest but not present")

    records = _read_jsonl(root / "evidence/audit.jsonl", "evidence/audit.jsonl")
    policy = _read_json(root / "evidence/policy.json", "evidence/policy.json")
    genesis = _read_json(root / "evidence/genesis.json", "evidence/genesis.json")

    if not isinstance(policy, dict):
        raise _Invalid("evidence/policy.json: top level is not a JSON object")
    if not isinstance(genesis, dict):
        raise _Invalid("evidence/genesis.json: top level is not a JSON object")
    if not isinstance(genesis.get("prev_hash"), str):
        raise _Invalid("evidence/genesis.json: 'prev_hash' is missing or not a string")

    for index, record in enumerate(records):
        schema = record.get("schema")
        if schema != M0_AUDIT_SCHEMA:
            raise _Invalid(
                f"evidence/audit.jsonl: record {index} declares unsupported schema "
                f"{schema!r} (this verifier implements {M0_AUDIT_SCHEMA})"
            )
        if "entry_hash" not in record:
            raise _Invalid(f"evidence/audit.jsonl: record {index} carries no entry_hash")

    return manifest, records, policy, genesis


def verify_package(package_root) -> VerificationResult:
    """Verify an M0 Evidence Package from its directory alone."""
    root = Path(package_root)

    try:
        manifest, records, policy, genesis = _check_structure(root)
    except _Invalid as exc:
        return VerificationResult(status=INVALID, reasons=(exc.reason,))

    package_id = manifest.get("package_id")
    failures: list[str] = []

    # 1. The manifest binds the bytes of every declared file.
    for relative, expected in sorted(manifest["files"].items()):
        target = root / relative
        if not target.is_file():
            failures.append(f"{relative}: declared in the manifest but not present")
            continue
        actual = _digest(target)
        if actual != expected:
            failures.append(
                f"{relative}: sha256 is {actual}, manifest declares {expected}"
            )

    # 2. The chain is anchored to the package's genesis record.
    anchor = genesis["prev_hash"]

    # 3. Every entry digest, and every link between consecutive entries. A record whose
    #    protected members cannot be canonicalised at all is not interpretable as
    #    evidence, so it downgrades the result to INVALID rather than failing integrity.
    try:
        verdict = verify_chain(records, genesis_prev_hash=anchor)
    except (ChainError, CanonicalisationError) as exc:
        return VerificationResult(
            status=INVALID,
            reasons=(f"evidence/audit.jsonl: {exc}",),
            package_id=package_id,
        )
    failures.extend(verdict.failures)

    # 4. Every entry names the policy document this package actually carries.
    try:
        expected_policy = policy_hash(policy)
    except CanonicalisationError as exc:
        return VerificationResult(
            status=INVALID,
            reasons=(f"evidence/policy.json: not canonicalisable ({exc})",),
            package_id=package_id,
        )
    for index, record in enumerate(records):
        if record.get("policy_hash") != expected_policy:
            failures.append(
                f"record {index}: policy_hash {record.get('policy_hash')!r} does not "
                f"match the policy document in this package ({expected_policy})"
            )

    if failures:
        return VerificationResult(
            status=TAMPERED,
            reasons=tuple(failures),
            package_id=package_id,
            entries=len(records),
        )

    return VerificationResult(status=VERIFIED, package_id=package_id, entries=len(records))
