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
    "DECISIONS",
    "CONFIDENCE_SCALE",
    "GENESIS_PREV_HASH",
    "confidence_to_basis_points",
    "Violation",
    "AuditEntry",
]


class ModelError(ValueError):
    """A value is outside the M0 evidence domain."""


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
