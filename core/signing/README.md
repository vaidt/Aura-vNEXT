# core/signing — deliberately unpopulated

**Status: NO M0 SCHEME DEFINED.**

M0 binds evidence with a canonical digest and a hash chain (ADR-0005). It defines **no
signature scheme**: no key format, no algorithm, no trust root, no revocation model, and
no timestamp authority.

This directory holds no implementation because none is decided. It exists so that the
absence is visible rather than inferred from a missing directory.

A signing scheme requires its own ADR before anything is placed here. Until then a
verified M0 package establishes **integrity** — the evidence is internally consistent and
has not been altered since it was sealed — and not **authenticity**, which would require
binding the seal to an identity. `app/verifier` states this distinction in its output and
must not be changed to imply otherwise.

Explicitly out of M0 scope, per the product boundary: RFC 3161 timestamping, PKIX/TSR,
and Merkle segment sealing.
