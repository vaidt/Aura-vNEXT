"""Aura vNEXT M0 core: canonical evidence domain.

Scope is fixed by docs/contract/M0-EVIDENCE-CONTRACT.md and ADR-0005: evidence
representation, canonical binding, and chain integrity. Concerns outside that contract
are not implemented here; ADR-0006 section 5 is the single place they are enumerated,
so that the list does not drift across restatements.
"""

M0_AUDIT_SCHEMA = "aura.audit/1"
M0_PACKAGE_PROFILE = "aura.evidence.package/1"
M0_CANONICAL_FORM = "AURA-CANON/1"
M0_DIGEST = "SHA-256"
