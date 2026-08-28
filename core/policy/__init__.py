"""Policy representation and its binding into the audit chain (ADR-0005).

M0 does not evaluate policy. It binds the policy document that a decision was taken
under, so that a verifier can establish *which* policy the evidence refers to without
running an engine. Evaluation semantics remain out of M0 scope entirely.
"""

from __future__ import annotations

import hashlib

from core.canonical import canonical_bytes

__all__ = ["policy_hash", "policy_preimage"]


def policy_preimage(policy_document: dict) -> bytes:
    """Return the canonical bytes of a policy document."""
    return canonical_bytes(policy_document)


def policy_hash(policy_document: dict) -> str:
    """Return the lowercase hex SHA-256 of a policy document's canonical bytes."""
    return hashlib.sha256(policy_preimage(policy_document)).hexdigest()
