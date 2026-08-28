"""The M0 evidence domain: decisions, violations, and audit entries (ADR-0005).

The domain deliberately holds only what M0 protects. What is excluded is enumerated
once, in ADR-0006 section 5, rather than restated here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Mapping, Sequence

from core import M0_AUDIT_SCHEMA

__all__ = [
    "ModelError",
    "SchemaError",
    "AUDIT_RECORD_FIELDS",
    "AUDIT_RECORD_INTEGRITY_FIELD",
    "VIOLATION_FIELDS",
    "validate_audit_record",
    "validate_audit_semantics",
    "DECISIONS",
    "CONFIDENCE_SCALE",
    "GENESIS_PREV_HASH",
    "confidence_to_basis_points",
    "Violation",
    "AuditEntry",
]


class ModelError(ValueError):
    """A value is outside the M0 evidence domain."""


class SchemaError(ModelError):
    """A record cannot be interpreted as an M0 audit record.

    Distinct from an integrity failure. This says "I cannot read this as evidence",
    which a verifier reports as INVALID; it never means "this evidence was altered".
    """


# The externally meaningful outcomes M0 records. Held closed: an unrecognised
# decision is a package this verifier cannot interpret, not one it guesses at.
DECISIONS = ("ALLOW", "DENY", "REQUIRE_APPROVAL")

# Confidence is carried as an integer count of ten-thousandths (basis points).
# 0.0 -> 0, 0.5 -> 5000, 0.95 -> 9500, 1.0 -> 10000.
CONFIDENCE_SCALE = 10000

# The chain predecessor of the first entry. Not a hash of anything -- a fixed
# sentinel, so that "no predecessor" is stated rather than implied by absence.
GENESIS_PREV_HASH = "0" * 64

_HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")
# RFC 3339 UTC, second precision, 'Z' only. A single spelling per instant: offsets
# and fractional seconds would let two representations of one instant produce two
# different digests.
_TIMESTAMP = re.compile(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")


def confidence_to_basis_points(value) -> int:
    """Convert a confidence in [0.0, 1.0] to an integer count of basis points.

    Conversion runs through ``Decimal(repr(float(value)))`` so the scaling is exact
    for the shortest decimal that round-trips the float, rather than depending on
    binary multiplication: 0.95 * 10000 is 9500.000000000002 in binary floating
    point, and rounding that is a coincidence rather than a rule.

    Ties round half-to-even. Non-finite and out-of-range values are rejected, never
    clamped -- a confidence that cannot be represented must not silently become 0 or
    10000 and then be sealed into evidence as though it had been supplied.
    """
    if isinstance(value, bool):
        raise ModelError("confidence must be a number, not a bool")
    if isinstance(value, int):
        as_decimal = Decimal(value)
    elif isinstance(value, float):
        if value != value:
            raise ModelError("confidence is NaN")
        if value in (float("inf"), float("-inf")):
            raise ModelError(f"confidence is non-finite: {value}")
        as_decimal = Decimal(repr(value))
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise ModelError(f"confidence is non-finite: {value}")
        as_decimal = value
    elif isinstance(value, str):
        # Accepted so a fixture can state an exact decimal that no float represents.
        try:
            as_decimal = Decimal(value)
        except InvalidOperation:
            raise ModelError(f"confidence is not a number: {value!r}") from None
        if not as_decimal.is_finite():
            raise ModelError(f"confidence is non-finite: {value}")
    else:
        raise ModelError(f"confidence has unsupported type {type(value).__name__}")

    if as_decimal < 0 or as_decimal > 1:
        raise ModelError(f"confidence {as_decimal} is outside [0.0, 1.0]")

    scaled = (as_decimal * CONFIDENCE_SCALE).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
    return int(scaled)


def _require_text(value, what: str) -> str:
    if not isinstance(value, str):
        raise ModelError(f"{what} must be a string, got {type(value).__name__}")
    return value


def _require_non_empty(value, what: str) -> str:
    text = _require_text(value, what)
    if not text:
        raise ModelError(f"{what} must not be empty")
    return text


def _require_hex64(value, what: str) -> str:
    text = _require_text(value, what)
    if not _HEX64.match(text):
        raise ModelError(f"{what} must be 64 lowercase hex characters, got {text!r}")
    return text


# ---------------------------------------------------------------------------
# The wire schema: a closed world.
#
# M0 is strict and deterministic. A member not named here cannot enter the
# protected domain, because there is no extension mechanism and no forward
# compatibility to negotiate. An unrecognised member therefore makes the record
# uninterpretable rather than being ignored -- if it were ignored it would be
# excluded from the preimage, and a record carrying undeclared content would still
# reach VERIFIED.
#
# AUDIT_RECORD_FIELDS declares presence and type only -- structural
# interpretability. The value domains are enforced separately, by
# validate_audit_semantics() below. Both are prerequisites for interpreting a
# record as an M0 AuditEntry at all, and both therefore classify as INVALID; the
# digest and the chain decide TAMPERED, and only for a record that is already a
# valid AuditEntry.
# ---------------------------------------------------------------------------

AUDIT_RECORD_INTEGRITY_FIELD = "entry_hash"

# name -> (type, required)
AUDIT_RECORD_FIELDS: dict[str, tuple[type, bool]] = {
    "schema": (str, True),
    "seq": (int, True),
    "request_id": (str, True),
    "timestamp": (str, True),
    "decision": (str, True),
    "policy_hash": (str, True),
    "policy_repr": (str, True),
    "input_hash": (str, True),
    "prev_hash": (str, True),
    "violations": (list, True),
    "metadata": (dict, True),
    "shadow_hash": (str, False),
    AUDIT_RECORD_INTEGRITY_FIELD: (str, True),
}

VIOLATION_FIELDS: dict[str, tuple[type, bool]] = {
    "rule": (str, True),
    "action": (str, True),
    "confidence": (int, True),
}


def _check_type(value, expected: type, what: str) -> None:
    # bool is a subclass of int, so an unguarded isinstance would accept `true` as a
    # sequence number or a confidence.
    if expected is int and isinstance(value, bool):
        raise SchemaError(f"{what} must be an integer, got bool")
    if not isinstance(value, expected):
        raise SchemaError(
            f"{what} must be {expected.__name__}, got {type(value).__name__}"
        )


def _validate_against(record: dict, fields: dict, what: str) -> None:
    if not isinstance(record, dict):
        raise SchemaError(f"{what} must be a JSON object, got {type(record).__name__}")

    for name, (expected, required) in fields.items():
        if name not in record:
            if required:
                raise SchemaError(f"{what}: required field {name!r} is missing")
            continue
        _check_type(record[name], expected, f"{what}.{name}")

    unknown = sorted(set(record) - set(fields))
    if unknown:
        raise SchemaError(
            f"{what}: unknown field(s) {', '.join(repr(u) for u in unknown)}; "
            f"M0 is a closed world and defines no extension mechanism"
        )


def validate_audit_record(record, *, where: str = "audit record") -> None:
    """Layer 1 -- structural interpretability: presence, type, closed world.

    Raises ``SchemaError`` on a missing required field, a wrong field type, or any
    unknown field, at the record level and within every violation. Called before
    canonical hashing, so a record that cannot be interpreted is never hashed and
    never reaches an integrity verdict.

    This layer says nothing about *values*; see ``validate_audit_semantics``.
    """
    _validate_against(record, AUDIT_RECORD_FIELDS, where)

    for index, violation in enumerate(record["violations"]):
        _validate_against(violation, VIOLATION_FIELDS, f"{where}.violations[{index}]")

    for key, value in record["metadata"].items():
        if not isinstance(key, str):
            raise SchemaError(f"{where}.metadata: key {key!r} is not a string")
        if not isinstance(value, str):
            raise SchemaError(
                f"{where}.metadata[{key!r}] must be str, got {type(value).__name__}"
            )


def validate_audit_semantics(record: dict, *, where: str = "audit record") -> None:
    """Layer 2 -- the semantic AuditEntry domain.

    Every member of an M0 audit entry has a value domain, stated in the contract's
    entry table: a closed decision vocabulary, one timestamp spelling, 64 lowercase
    hex for every digest, a non-negative sequence number, non-empty identifiers, and
    confidence in [0, CONFIDENCE_SCALE]. A record violating one of them is not an
    M0 AuditEntry, whatever its shape.

    Such a record is INVALID, not TAMPERED. Being hashable is not the same as being
    interpretable: a record carrying ``decision = "WHATEVER"`` can be canonicalised,
    sealed with a correct digest, and linked into a chain, and it would then present
    as intact evidence for a decision M0 does not define. TAMPERED is reserved for a
    record that *is* a valid AuditEntry whose protected content no longer matches
    its committed binding.

    Assumes ``validate_audit_record`` has already passed, so presence and types are
    established and only values are examined here.

    Raises ``SchemaError``.
    """
    def fail(detail: str) -> None:
        raise SchemaError(f"{where}: {detail}")

    if record["decision"] not in DECISIONS:
        fail(f"decision {record['decision']!r} is not one of {', '.join(DECISIONS)}")

    if not _TIMESTAMP.match(record["timestamp"]):
        fail(f"timestamp {record['timestamp']!r} is not RFC 3339 UTC to the second "
             f"(YYYY-MM-DDThh:mm:ssZ)")

    for name in ("policy_hash", "input_hash", "prev_hash",
                 AUDIT_RECORD_INTEGRITY_FIELD):
        if not _HEX64.match(record[name]):
            fail(f"{name} {record[name]!r} is not 64 lowercase hex characters")

    # Optional, but constrained when present.
    if "shadow_hash" in record and not _HEX64.match(record["shadow_hash"]):
        fail(f"shadow_hash {record['shadow_hash']!r} is not 64 lowercase hex characters")

    if record["seq"] < 0:
        fail(f"seq {record['seq']} is negative")

    if not record["request_id"]:
        fail("request_id is empty")

    if not record["schema"]:
        fail("schema is empty")

    for index, violation in enumerate(record["violations"]):
        at = f"violations[{index}]"
        if not violation["rule"]:
            fail(f"{at}.rule is empty")
        if not violation["action"]:
            fail(f"{at}.action is empty")
        confidence = violation["confidence"]
        if not 0 <= confidence <= CONFIDENCE_SCALE:
            fail(f"{at}.confidence {confidence} is outside [0, {CONFIDENCE_SCALE}]")


@dataclass(frozen=True)
class Violation:
    """One policy violation recorded against a decision.

    Every field is protected. Violations are held in the order the producer recorded
    them; that order is part of the evidence, so reordering is a mutation.
    """

    rule: str
    action: str
    confidence: int

    @classmethod
    def build(cls, rule: str, action: str, confidence) -> "Violation":
        """Construct from a producer-supplied confidence of any accepted numeric form."""
        return cls(
            rule=_require_non_empty(rule, "violation.rule"),
            action=_require_non_empty(action, "violation.action"),
            confidence=confidence_to_basis_points(confidence),
        )

    def canonical_representation(self) -> dict:
        if not isinstance(self.confidence, int) or isinstance(self.confidence, bool):
            raise ModelError("violation.confidence must already be integer basis points")
        if not 0 <= self.confidence <= CONFIDENCE_SCALE:
            raise ModelError(f"violation.confidence {self.confidence} out of range")
        return {
            "action": _require_non_empty(self.action, "violation.action"),
            "confidence": self.confidence,
            "rule": _require_non_empty(self.rule, "violation.rule"),
        }


@dataclass(frozen=True)
class AuditEntry:
    """One protected link in the audit chain.

    Every field on this type participates in the digest. The digest itself is not a
    field: see ``core.chain.entry_hash``.
    """

    seq: int
    request_id: str
    timestamp: str
    decision: str
    policy_hash: str
    policy_repr: str
    input_hash: str
    prev_hash: str
    violations: Sequence[Violation] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    shadow_hash: str | None = None
    schema: str = M0_AUDIT_SCHEMA

    def canonical_representation(self) -> dict:
        """Return the protected representation -- the input to canonicalisation.

        This mapping is the whole of what the digest binds. It never contains the
        digest: the integrity value cannot participate in its own preimage, so it is
        not merely omitted here but has no representation to omit.
        """
        if isinstance(self.seq, bool) or not isinstance(self.seq, int):
            raise ModelError("seq must be an integer")
        if self.seq < 0:
            raise ModelError(f"seq must not be negative, got {self.seq}")
        if self.decision not in DECISIONS:
            raise ModelError(
                f"decision {self.decision!r} is not one of {', '.join(DECISIONS)}"
            )
        if not _TIMESTAMP.match(_require_text(self.timestamp, "timestamp")):
            raise ModelError(
                f"timestamp {self.timestamp!r} is not RFC 3339 UTC to the second (…Z)"
            )

        representation = {
            "decision": self.decision,
            "input_hash": _require_hex64(self.input_hash, "input_hash"),
            "policy_hash": _require_hex64(self.policy_hash, "policy_hash"),
            "policy_repr": _require_text(self.policy_repr, "policy_repr"),
            "prev_hash": _require_hex64(self.prev_hash, "prev_hash"),
            "request_id": _require_non_empty(self.request_id, "request_id"),
            "schema": _require_non_empty(self.schema, "schema"),
            "seq": self.seq,
            "timestamp": self.timestamp,
            "violations": [v.canonical_representation() for v in self.violations],
        }

        # Optional members are present or absent, never null. An absent shadow_hash
        # and a shadow_hash of "" are therefore different canonical byte strings --
        # the None / Some("") distinction the domain is required to preserve.
        if self.shadow_hash is not None:
            representation["shadow_hash"] = _require_hex64(self.shadow_hash, "shadow_hash")

        metadata = dict(self.metadata)
        for key, value in metadata.items():
            _require_text(key, "metadata key")
            _require_text(value, f"metadata[{key!r}]")
        representation["metadata"] = metadata

        return representation
