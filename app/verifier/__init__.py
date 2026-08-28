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
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core import M0_AUDIT_SCHEMA, M0_CANONICAL_FORM, M0_DIGEST, M0_PACKAGE_PROFILE
from core.canonical import CanonicalisationError
from core.chain import ChainError, verify_chain
from core.models import (SchemaError, validate_audit_record,
                         validate_audit_semantics)
from core.policy import policy_hash

__all__ = ["VERIFIED", "TAMPERED", "INVALID", "DECLARED_CONTRACT",
           "REQUIRED_FILES", "VerificationResult", "verify_package"]

VERIFIED = "VERIFIED"
TAMPERED = "TAMPERED"
INVALID = "INVALID"

REQUIRED_FILES = ("evidence/audit.jsonl", "evidence/policy.json", "evidence/genesis.json")

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")

# The verification contract a package declares in its manifest. The verifier must
# reject a declaration it does not implement rather than proceeding on the
# assumption that the package meant this one: a package declaring a different
# canonical form or digest is asking for a verification this build cannot perform.
DECLARED_CONTRACT = {
    "profile": M0_PACKAGE_PROFILE,
    "audit_schema": M0_AUDIT_SCHEMA,
    "canonical_form": M0_CANONICAL_FORM,
    "digest": M0_DIGEST,
}

# expected/result.json is NON-NORMATIVE test fixture metadata
# (docs/contract/M0-EVIDENCE-CONTRACT.md section 6.2). It is deliberately absent
# from REQUIRED_FILES and from the manifest's digest set: the verifier never reads
# it, and a package's own claim about its verdict has no bearing on the verdict it
# receives. A verifier that trusted it could be told what to conclude.


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


def _package_file(root: Path, relative, label: str) -> Path:
    """Resolve a manifest-declared path, refusing anything outside the package.

    The manifest is untrusted input: it travels with the evidence and is written
    by whoever produced or last touched the package. A declared path is therefore
    an instruction from the package about which files to read, and M0's claim is
    that a verifier operates from the package alone. A path that escapes the
    package root breaks that claim before any digest is computed -- the verifier
    would already have read something outside the trust boundary.

    ``root / relative`` alone is not containment. ``Path("/pkg") / "../x"`` stays
    lexically inside but resolves out, and ``Path("/pkg") / "/etc/x"`` discards
    the root entirely and yields ``/etc/x``.

    Two checks, both required:

      * the spelling must be a plain relative POSIX path with no traversal
        component -- refused without touching the filesystem;
      * the resolved target must lie strictly inside the resolved root, which is
        what catches a symlink whose target leaves the package.

    An escape is INVALID, not TAMPERED: a package instructing the verifier to
    read outside itself is not a recognisable M0 Evidence Package whose evidence
    happens to fail integrity. It is not one at all.
    """
    if not isinstance(relative, str) or not relative:
        raise _Invalid(f"{label}: declared file path is empty or not a string")

    # Backslash is a separator on some platforms; a path carrying one is not the
    # plain POSIX relative path the package format specifies.
    if "\\" in relative:
        raise _Invalid(
            f"{label}: declared file path {relative!r} contains a backslash; "
            f"package paths are relative POSIX paths"
        )

    pure = PurePosixPath(relative)
    if pure.is_absolute():
        raise _Invalid(
            f"{label}: declared file path {relative!r} is absolute; package paths "
            f"must be relative to the package root"
        )
    for part in pure.parts:
        if part == "..":
            raise _Invalid(
                f"{label}: declared file path {relative!r} contains a '..' "
                f"component; package paths must not traverse"
            )

    # The spelling must already be canonical. PurePosixPath silently drops '.'
    # segments, duplicate slashes and trailing slashes, so a component scan alone
    # does not see them -- './evidence/policy.json' reaches this point looking
    # like a plain path. They are refused rather than normalised because a
    # manifest is a map keyed by these strings: two spellings of one file would
    # be two entries able to declare two different digests for the same bytes,
    # and REQUIRED_FILES membership is tested by exact string.
    if str(pure) != relative:
        raise _Invalid(
            f"{label}: declared file path {relative!r} is not in canonical form "
            f"(expected {str(pure)!r}); package paths carry no '.' segments, "
            f"repeated separators, or trailing separator"
        )

    base = root.resolve()
    # resolve() follows symlinks, so a package-local link pointing outside the
    # package resolves to its real target and fails the containment check below.
    target = (root / pure).resolve()
    if target == base or not target.is_relative_to(base):
        raise _Invalid(
            f"{label}: declared file path {relative!r} resolves to {target}, "
            f"which is outside the evidence package at {base}"
        )
    return target


def _check_structure(root: Path) -> tuple[dict, list, dict, dict]:
    """Establish that this is an M0 package. Every failure here means INVALID."""
    if not root.is_dir():
        raise _Invalid(f"{root}: not a directory")

    manifest = _read_json(root / "manifest.json", "manifest.json")
    if not isinstance(manifest, dict):
        raise _Invalid("manifest.json: top level is not a JSON object")

    for name, supported in DECLARED_CONTRACT.items():
        declared = manifest.get(name)
        if declared is None:
            raise _Invalid(f"manifest.json: does not declare {name!r}")
        if declared != supported:
            raise _Invalid(
                f"manifest.json: unsupported {name} {declared!r} "
                f"(this verifier implements {supported!r})"
            )

    files = manifest.get("files")
    if not isinstance(files, dict):
        raise _Invalid("manifest.json: 'files' is missing or is not an object")

    # The chain terminus declarations. Malformed or missing is a manifest this
    # verifier cannot interpret (INVALID); a well-formed declaration that does not
    # match the evidence is checked later, against the parsed chain (TAMPERED).
    chain_head = manifest.get("chain_head")
    if not isinstance(chain_head, str) or not _HEX64.match(chain_head):
        raise _Invalid(
            f"manifest.json: 'chain_head' is missing or is not 64 lowercase hex "
            f"characters (got {chain_head!r})"
        )
    entry_count = manifest.get("entry_count")
    if isinstance(entry_count, bool) or not isinstance(entry_count, int):
        raise _Invalid(
            f"manifest.json: 'entry_count' is missing or is not an integer "
            f"(got {entry_count!r})"
        )
    if entry_count < 1:
        raise _Invalid(
            f"manifest.json: 'entry_count' is {entry_count}; a package declaring no "
            f"audit records is not an M0 Evidence Package"
        )

    # Every manifest-declared path is checked for containment before anything is
    # read, so a path that escapes the package can never reach a digest.
    for declared in sorted(files):
        _package_file(root, declared, "manifest.json")

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
        # Both interpretability layers run before any canonicalisation or hashing,
        # so a record that is not an M0 AuditEntry never reaches an integrity
        # verdict -- in particular it cannot reach VERIFIED by being sealed
        # correctly over content M0 does not define.
        #
        #   layer 1  structure  presence, type, closed world
        #   layer 2  semantics  value domains of the entry table
        #
        # Both are prerequisites for the record being an AuditEntry at all, so both
        # are INVALID. TAMPERED belongs to the integrity checks further down, and
        # applies only to a record that is already a valid AuditEntry.
        where = f"evidence/audit.jsonl record {index}"
        try:
            validate_audit_record(record, where=where)
            validate_audit_semantics(record, where=where)
        except SchemaError as exc:
            raise _Invalid(str(exc)) from exc

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
    #
    # _check_structure has already refused any path that escapes the package, so
    # the re-resolution below cannot fail. It is kept, and its failure handled,
    # so that the digest is always taken from a contained path: if the two checks
    # ever drift apart, the result is INVALID rather than a crash or a read
    # outside the package.
    try:
        for relative, expected in sorted(manifest["files"].items()):
            target = _package_file(root, relative, "manifest.json")
            if not target.is_file():
                failures.append(f"{relative}: declared in the manifest but not present")
                continue
            actual = _digest(target)
            if actual != expected:
                failures.append(
                    f"{relative}: sha256 is {actual}, manifest declares {expected}"
                )
    except _Invalid as exc:
        return VerificationResult(status=INVALID, reasons=(exc.reason,),
                                  package_id=package_id)

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
    # verify_chain reports a failure against a record index ("record 2: ..."), which
    # is unambiguous inside core.chain and not to an operator holding a package of
    # four files. Every reason this verifier emits names the file it concerns, so
    # the chain's findings are given the same treatment here rather than in
    # core.chain, which has no notion of a package to name a file within.
    failures.extend(f"evidence/audit.jsonl: {failure}" for failure in verdict.failures)

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
                f"evidence/audit.jsonl: record {index}: policy_hash "
                f"{record.get('policy_hash')!r} does not match the policy document "
                f"in this package ({expected_policy})"
            )

    # 5. The declared chain terminus. Without this the chain is bound only
    #    backwards: the final record has nothing linking forward from it, so it can
    #    be rewritten and resealed, and records can be dropped from the end, with
    #    every remaining link still consistent. Both declarations are compared
    #    against the parsed chain, so a mismatch is a recognisable M0 package whose
    #    evidence no longer matches what it committed to -- TAMPERED, not INVALID.
    if len(records) != manifest["entry_count"]:
        failures.append(
            f"evidence/audit.jsonl: contains {len(records)} record(s), manifest "
            f"declares entry_count {manifest['entry_count']}"
        )
    if records[-1]["entry_hash"] != manifest["chain_head"]:
        failures.append(
            f"evidence/audit.jsonl: final record entry_hash "
            f"{records[-1]['entry_hash']} does not match the declared chain_head "
            f"{manifest['chain_head']}"
        )

    if failures:
        return VerificationResult(
            status=TAMPERED,
            reasons=tuple(failures),
            package_id=package_id,
            entries=len(records),
        )

    return VerificationResult(status=VERIFIED, package_id=package_id, entries=len(records))
