"""Producing an M0 Evidence Package from an application event (ADR-0006).

This module is the operational path M0 left open. The contract established what a
package *is* and what a verifier may conclude from one; it did not establish how an
application that takes decisions turns one of those decisions into a package. Without
that path the only way to obtain evidence is to hand-write a fixture, which is not a
product.

    application event -> AuditEntry -> sealed record -> chain -> Evidence Package

**This is an adapter, not a specification.** It defines no evidence semantics of its
own. Every protected value it writes is computed by the accepted M0 implementation:

    core.models     the AuditEntry domain and its value rules
    core.canonical  AURA-CANON/1
    core.chain      the entry digest, the seal, and chain linkage
    core.policy     the policy binding

Nothing here re-implements canonicalisation, hashing, or linkage, and nothing here
adds a member to the protected domain. If a value is protected, it came from `core`.

What this module *does* own is the package's **serialised form** -- how the sealed
records, the policy document, the anchor, and the manifest are laid out as bytes on
disk. That layout is the same one `tools/build_m0_fixtures.py` used to carry inline,
and it now lives here alone, so the reference package and any package an application
produces are built by one code path rather than two that must be kept in step.

The producer is deliberately absent from the verifier's environment
(`tools/independence_check.py`): a package that needed this module to be verified
would not be independent evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from core import M0_AUDIT_SCHEMA, M0_CANONICAL_FORM, M0_DIGEST, M0_PACKAGE_PROFILE
from core.canonical import CanonicalisationError
from core.chain import seal, verify_chain
from core.models import GENESIS_PREV_HASH, AuditEntry, ModelError, Violation
from core.policy import policy_hash

__all__ = [
    "ProducerError",
    "DecisionEvent",
    "GENESIS_NOTE",
    "input_digest",
    "derive_policy_repr",
    "build_package",
    "append_event",
    "write_package",
    "read_package",
]


class ProducerError(ValueError):
    """An application event cannot be recorded as M0 evidence.

    Raised before anything is written. A producer that emitted a package it could not
    itself verify would be manufacturing evidence of its own failure, so every refusal
    happens while the package is still a mapping in memory.
    """


# The anchor's explanatory note. Fixed text: the anchor file is digested by the
# manifest, so its bytes are part of what a package commits to.
GENESIS_NOTE = "Chain anchor. Not a digest of anything; a stated absence of predecessor."


@dataclass(frozen=True)
class DecisionEvent:
    """One application decision, in the form an application already has it.

    This is the producer's input, not a protected structure: it carries exactly what
    is needed to construct an ``AuditEntry`` and nothing more. ``seq`` and
    ``prev_hash`` are deliberately absent -- they are chain position, which the
    producer assigns, not facts the application is entitled to state.

    ``confidence`` on a violation is accepted in any form ``core.models`` accepts
    (a float, an int, a Decimal, or an exact decimal string) and is converted there.
    """

    request_id: str
    timestamp: str
    decision: str
    input_hash: str
    policy_repr: str = ""
    violations: Sequence[Mapping] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    shadow_hash: str | None = None

    @classmethod
    def from_mapping(cls, data: Mapping) -> "DecisionEvent":
        """Build an event from a plain mapping, e.g. one decoded from JSON."""
        if not isinstance(data, Mapping):
            raise ProducerError(
                f"an event must be a JSON object, got {type(data).__name__}"
            )
        known = {
            "request_id", "timestamp", "decision", "input_hash", "policy_repr",
            "violations", "metadata", "shadow_hash",
        }
        unknown = sorted(set(data) - known)
        if unknown:
            raise ProducerError(
                f"event carries unknown field(s) {', '.join(repr(u) for u in unknown)}; "
                f"the producer adds no members to the M0 audit entry, so a field it "
                f"does not recognise would be silently dropped from the evidence"
            )
        for required in ("request_id", "timestamp", "decision", "input_hash"):
            if required not in data:
                raise ProducerError(f"event is missing required field {required!r}")
        return cls(
            request_id=data["request_id"],
            timestamp=data["timestamp"],
            decision=data["decision"],
            input_hash=data["input_hash"],
            policy_repr=data.get("policy_repr", ""),
            violations=list(data.get("violations", ())),
            metadata=dict(data.get("metadata", {})),
            shadow_hash=data.get("shadow_hash"),
        )


def input_digest(data: bytes) -> str:
    """Return the digest of a decision input held as bytes.

    M0 records an input *reference*: the entry carries a 64-hex digest and the
    contract says nothing about how it was derived, because the input itself never
    enters the package. This helper is therefore a producer-side convenience for the
    common case where the caller has the input as a local file, not a new protocol
    rule -- an application that already computes its own input digest passes it
    straight through instead.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise ProducerError(f"input must be bytes, got {type(data).__name__}")
    return hashlib.sha256(bytes(data)).hexdigest()


def derive_policy_repr(policy_document: Mapping) -> str:
    """Return a human-readable policy label derived from the document, or ``""``.

    ``policy_repr`` is protected but has no value constraint: the contract allows any
    string, including an empty one. The binding that matters is ``policy_hash``, so
    this label exists for a human reading the evidence. It is derived only when the
    document states both members unambiguously; otherwise the caller supplies it.
    """
    if not isinstance(policy_document, Mapping):
        return ""
    identifier = policy_document.get("policy_id")
    version = policy_document.get("version")
    if isinstance(identifier, str) and identifier and isinstance(version, (int, str)):
        if isinstance(version, bool):
            return ""
        return f"{identifier}/{version}"
    return ""


def _violation(raw) -> Violation:
    if not isinstance(raw, Mapping):
        raise ProducerError(
            f"a violation must be an object with 'rule', 'action' and 'confidence', "
            f"got {type(raw).__name__}"
        )
    unknown = sorted(set(raw) - {"rule", "action", "confidence"})
    if unknown:
        raise ProducerError(
            f"violation carries unknown field(s) {', '.join(repr(u) for u in unknown)}"
        )
    for required in ("rule", "action", "confidence"):
        if required not in raw:
            raise ProducerError(f"violation is missing required field {required!r}")
    try:
        return Violation.build(raw["rule"], raw["action"], raw["confidence"])
    except ModelError as exc:
        raise ProducerError(str(exc)) from exc


def _entry_for(event: DecisionEvent, *, seq: int, prev_hash: str,
               computed_policy_hash: str) -> AuditEntry:
    """Construct the AuditEntry for one event at one chain position.

    Chain position is supplied by the caller, never taken from the event: an
    application that could choose its own ``seq`` and ``prev_hash`` could place a
    record anywhere in the chain, which is the producer's decision to make.
    """
    return AuditEntry(
        seq=seq,
        request_id=event.request_id,
        timestamp=event.timestamp,
        decision=event.decision,
        policy_hash=computed_policy_hash,
        policy_repr=event.policy_repr,
        input_hash=event.input_hash,
        prev_hash=prev_hash,
        violations=[_violation(v) for v in event.violations],
        metadata=dict(event.metadata),
        shadow_hash=event.shadow_hash,
        schema=M0_AUDIT_SCHEMA,
    )


# ---------------------------------------------------------------------------
# Serialised form.
#
# These four functions are the only place the package's bytes are decided. The
# digests inside those bytes all come from `core`; what is fixed here is layout:
# one compact JSON object per line for the chain, indented documents elsewhere, and
# a trailing newline on every file so the package is readable with ordinary tools.
# ---------------------------------------------------------------------------

def _document_bytes(document) -> bytes:
    return (json.dumps(document, sort_keys=True, indent=2) + "\n").encode("utf-8")


def serialise_records(records: Sequence[Mapping]) -> bytes:
    """Return the bytes of ``evidence/audit.jsonl``: one sealed record per line.

    ``ensure_ascii=False`` keeps non-ASCII text as itself rather than as escapes.
    This is the package's transport encoding and is not the hash preimage -- the
    preimage is AURA-CANON/1, produced by ``core.canonical`` -- so a verifier
    re-derives each digest from the decoded record, never from this line.
    """
    return ("\n".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        for record in records
    ) + "\n").encode("utf-8")


def serialise_genesis(package_id: str, anchor: str = GENESIS_PREV_HASH) -> bytes:
    """Return the bytes of ``evidence/genesis.json``: the chain anchor."""
    return _document_bytes({
        "package_id": package_id,
        "prev_hash": anchor,
        "note": GENESIS_NOTE,
    })


def build_manifest(package_id: str, records: Sequence[Mapping],
                   files: Mapping[str, bytes]) -> dict:
    """Return the manifest binding this package's contract, terminus, and bytes.

    ``chain_head`` and ``entry_count`` are the chain terminus. Without them the chain
    is bound only backwards: the last record has nothing linking forward from it, so
    it could be rewritten, or records dropped from the end, with every remaining link
    still consistent. ``chain_head`` is the final record's own ``entry_hash``, so this
    introduces no second hashing domain.
    """
    return {
        "profile": M0_PACKAGE_PROFILE,
        "package_id": package_id,
        "audit_schema": M0_AUDIT_SCHEMA,
        "canonical_form": M0_CANONICAL_FORM,
        "digest": M0_DIGEST,
        "chain_head": records[-1]["entry_hash"],
        "entry_count": len(records),
        "files": {
            name: hashlib.sha256(data).hexdigest()
            for name, data in sorted(files.items())
        },
    }


def _assemble(package_id: str, policy_document: Mapping,
              records: Sequence[Mapping], anchor: str) -> dict[str, bytes]:
    """Lay out a verified chain as the package's files."""
    files = {
        "evidence/audit.jsonl": serialise_records(records),
        "evidence/policy.json": _document_bytes(policy_document),
        "evidence/genesis.json": serialise_genesis(package_id, anchor),
    }
    files["manifest.json"] = _document_bytes(build_manifest(package_id, records, files))
    return files


def _seal_chain(events: Iterable[DecisionEvent], *, computed_policy_hash: str,
                records: list[dict], anchor: str) -> list[dict]:
    """Seal each event onto the end of ``records`` and return the extended chain."""
    chain = list(records)
    for event in events:
        if not isinstance(event, DecisionEvent):
            raise ProducerError(
                f"expected a DecisionEvent, got {type(event).__name__}"
            )
        previous = chain[-1]["entry_hash"] if chain else anchor
        entry = _entry_for(
            event, seq=len(chain), prev_hash=previous,
            computed_policy_hash=computed_policy_hash,
        )
        try:
            chain.append(seal(entry))
        except (ModelError, CanonicalisationError) as exc:
            raise ProducerError(
                f"event {event.request_id!r} is outside the M0 evidence domain: {exc}"
            ) from exc
    return chain


def _self_verify(records: Sequence[Mapping], anchor: str) -> None:
    """Refuse to emit a chain this implementation would not accept.

    Uses the verifier's own chain check rather than a producer-side re-derivation, so
    "the producer thinks it is valid" and "the verifier accepts it" cannot diverge.
    """
    verdict = verify_chain(list(records), genesis_prev_hash=anchor)
    if not verdict.ok:
        raise ProducerError(
            "the producer built a chain that does not verify: "
            + "; ".join(verdict.failures)
        )


def build_package(package_id: str, policy_document: Mapping,
                  events: Iterable[DecisionEvent],
                  *, anchor: str = GENESIS_PREV_HASH) -> dict[str, bytes]:
    """Build a complete Evidence Package as a ``relative path -> bytes`` mapping.

    Returns bytes rather than writing, so the same construction serves an application
    recording a decision, a test asserting against the result, and the fixture
    generator -- without one of them being a second implementation of the layout.
    """
    if not isinstance(package_id, str) or not package_id:
        raise ProducerError("package_id must be a non-empty string")
    if not isinstance(policy_document, Mapping):
        raise ProducerError(
            f"the policy document must be a JSON object, got "
            f"{type(policy_document).__name__}"
        )
    try:
        computed_policy_hash = policy_hash(policy_document)
    except CanonicalisationError as exc:
        raise ProducerError(f"the policy document has no canonical form: {exc}") from exc

    records = _seal_chain(events, computed_policy_hash=computed_policy_hash,
                          records=[], anchor=anchor)
    if not records:
        raise ProducerError(
            "no events were supplied; a package declaring no audit records is not an "
            "M0 Evidence Package"
        )
    _self_verify(records, anchor)
    return _assemble(package_id, policy_document, records, anchor)


def read_package(root) -> dict:
    """Read an existing package's chain, policy, anchor, and identity.

    Used to continue a chain across separate producer invocations, which is the
    ordinary case: an application records one decision now and another later, and the
    second must link to the first.
    """
    root = Path(root)
    manifest = _load_json(root / "manifest.json", "manifest.json")
    genesis = _load_json(root / "evidence/genesis.json", "evidence/genesis.json")
    policy = _load_json(root / "evidence/policy.json", "evidence/policy.json")

    audit_path = root / "evidence/audit.jsonl"
    if not audit_path.is_file():
        raise ProducerError("evidence/audit.jsonl: required file is missing")
    records = []
    for number, line in enumerate(
        audit_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ProducerError(
                f"evidence/audit.jsonl: malformed JSON on line {number} ({exc.msg})"
            ) from exc
    if not records:
        raise ProducerError("evidence/audit.jsonl: contains no audit records")

    anchor = genesis.get("prev_hash")
    if not isinstance(anchor, str):
        raise ProducerError("evidence/genesis.json: 'prev_hash' is missing or not a string")
    package_id = manifest.get("package_id")
    if not isinstance(package_id, str) or not package_id:
        raise ProducerError("manifest.json: 'package_id' is missing or not a string")

    return {
        "package_id": package_id,
        "policy": policy,
        "anchor": anchor,
        "records": records,
    }


def _load_json(path: Path, label: str):
    if not path.is_file():
        raise ProducerError(f"{label}: required file is missing")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProducerError(f"{label}: malformed JSON ({exc.msg})") from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise ProducerError(f"{label}: not readable as UTF-8 ({exc})") from exc
    if not isinstance(document, dict):
        raise ProducerError(f"{label}: top level is not a JSON object")
    return document


def append_event(root, event: DecisionEvent, *,
                 policy_document: Mapping | None = None) -> dict[str, bytes]:
    """Extend an existing package with one more decision.

    The new record takes the next sequence number and links to the current chain
    head, both read from the package on disk. The policy document is the one the
    package already carries: a caller may pass it to be checked, but may not swap it,
    because every record in a package is bound to a single policy document and the
    verifier checks exactly that.
    """
    existing = read_package(root)
    if policy_document is not None and policy_document != existing["policy"]:
        raise ProducerError(
            "the supplied policy document differs from the one this package already "
            "carries; every record in a package is bound to one policy document, so "
            "recording under a different policy needs a new package"
        )

    policy = existing["policy"]
    anchor = existing["anchor"]
    records = _seal_chain(
        [event], computed_policy_hash=policy_hash(policy),
        records=existing["records"], anchor=anchor,
    )
    _self_verify(records, anchor)
    return _assemble(existing["package_id"], policy, records, anchor)


def write_package(root, files: Mapping[str, bytes]) -> Path:
    """Write a package mapping to ``root`` and return the package directory."""
    root = Path(root)
    for relative, data in sorted(files.items()):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root
