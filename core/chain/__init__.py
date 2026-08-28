"""Audit chain integrity: entry digests and their linkage (ADR-0005).

The invariant this module exists to hold:

    AuditEntry -> canonical representation -> canonical bytes -> SHA-256

and, critically, the integrity value is computed over the representation that does
not contain it:

    H(canonical(AuditEntry without integrity hash))

never H(canonical(AuditEntry)) where the latter already carries the result.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from core.canonical import canonical_bytes
from core.models import GENESIS_PREV_HASH, AuditEntry, ModelError

__all__ = [
    "ChainError",
    "entry_preimage",
    "entry_hash",
    "seal",
    "verify_entry",
    "verify_chain",
    "ChainVerdict",
]


class ChainError(ValueError):
    """The chain cannot be interpreted -- distinct from the chain failing to verify."""


def entry_preimage(entry: AuditEntry) -> bytes:
    """Return the exact bytes hashed for ``entry``.

    Exposed deliberately: a conformance vector that records only a digest cannot show
    where two implementations diverge, and cannot be reviewed by a human at all.
    """
    return canonical_bytes(entry.canonical_representation())


def entry_hash(entry: AuditEntry) -> str:
    """Return the lowercase hex SHA-256 of the entry's canonical preimage."""
    return hashlib.sha256(entry_preimage(entry)).hexdigest()


def seal(entry: AuditEntry) -> dict:
    """Return the wire form of ``entry``: its protected representation plus the digest.

    The digest is attached under ``entry_hash`` *outside* the protected representation.
    Re-deriving it means dropping that member and canonicalising what remains, which
    is why the member can never influence its own value.
    """
    record = dict(entry.canonical_representation())
    record["entry_hash"] = entry_hash(entry)
    return record


def verify_entry(record: dict) -> bool:
    """Recompute the digest of a sealed record and compare it to the one carried.

    ``record`` is a wire-form mapping, not an ``AuditEntry``: verification must work
    from what the package actually contains, not from a producer-side object.
    """
    if not isinstance(record, dict):
        raise ChainError("sealed record must be a JSON object")
    if "entry_hash" not in record:
        raise ChainError("sealed record carries no entry_hash")

    claimed = record["entry_hash"]
    if not isinstance(claimed, str):
        raise ChainError("entry_hash must be a string")

    protected = {k: v for k, v in record.items() if k != "entry_hash"}
    computed = hashlib.sha256(canonical_bytes(protected)).hexdigest()
    return _constant_time_equal(computed, claimed)


def _constant_time_equal(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


@dataclass(frozen=True)
class ChainVerdict:
    ok: bool
    failures: tuple[str, ...] = ()


def verify_chain(records: list, genesis_prev_hash: str = GENESIS_PREV_HASH) -> ChainVerdict:
    """Verify every entry digest and every link between consecutive entries.

    Returns a verdict rather than raising, because a broken chain is an expected
    outcome that the caller must classify. Records that cannot be read *as* records
    raise ``ChainError`` instead: that is a different question with a different answer.
    """
    if not isinstance(records, list):
        raise ChainError("audit chain must be a list of sealed records")
    if not records:
        raise ChainError("audit chain is empty")

    failures: list[str] = []
    expected_prev = genesis_prev_hash

    for index, record in enumerate(records):
        try:
            digest_ok = verify_entry(record)
        except ChainError:
            raise
        except ModelError as exc:
            raise ChainError(f"record {index}: {exc}") from exc

        if not digest_ok:
            failures.append(f"record {index}: entry_hash does not match its canonical bytes")

        seq = record.get("seq")
        if seq != index:
            failures.append(f"record {index}: seq is {seq!r}, expected {index}")

        prev = record.get("prev_hash")
        if prev != expected_prev:
            failures.append(
                f"record {index}: prev_hash {prev!r} does not link to {expected_prev!r}"
            )

        # Link forward on the *claimed* digest. Using the recomputed one would let a
        # tampered entry re-link the rest of the chain around itself.
        expected_prev = record.get("entry_hash")

    return ChainVerdict(ok=not failures, failures=tuple(failures))
