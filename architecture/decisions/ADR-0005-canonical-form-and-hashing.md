# ADR-0005 — AURA-CANON/1: the canonical form and the integrity binding

- **Status:** ACCEPTED
- **Date:** 2026-08-27
- **Closes:** OQ-7; OQ-6 (for M0 scope)

## Context

OQ-7 asks which canonical form and which primitives underpin the audit chain and
evidence integrity. It is the decision M0 exists to make: every other M0 property —
chain integrity, the evidence package, independent verification — is defined in terms
of it.

**No prior specification was available to this decision.** The frozen `Aura-IDToken`
corpus is not reachable from this environment (`provenance/CORPUS-INDEX.md` §2), and
`governance/REPOSITORY-BOUNDARY.md` forbids reaching for it. No governing specification,
conformance vector, or normative text describing a prior Aura canonical form exists in
this repository.

AURA-CANON/1 is therefore **defined here**, not recovered. Per `governance/GENESIS.md`
§5, its authority is this ADR together with the vectors in `conformance/vectors/` — not
provenance, and not resemblance to anything that came before.

## Decision

### 1. Canonical form

**AURA-CANON/1** is a restricted profile of **RFC 8785 (JSON Canonicalization Scheme)**:

- output is UTF-8, with no insignificant whitespace;
- object members are sorted by the **UTF-16 code-unit sequence** of their names;
- strings are escaped per RFC 8785 §3.2.2.2: `"` and `\` and the C0 controls, with the
  short forms `\b \t \n \f \r` preferred and `\u00xx` otherwise; every other character,
  including all non-ASCII, is emitted literally.

RFC 8785 is chosen because it is a retrievable, externally maintained specification —
the authority basis `governance/GENESIS.md` §5 requires — rather than a format invented
for this repository and documented only by its own implementation.

### 2. Two restrictions on top of RFC 8785

- **No floating point.** Numbers are integers only. RFC 8785's most intricate area is
  ECMAScript number formatting; M0 removes the problem from the domain instead of
  implementing it carefully. Any real-valued quantity enters with a declared integer
  scale (§5).
- **No null.** An absent optional value is an **absent member**. This is what keeps
  `None` distinguishable from `Some("")`: absence changes the member set, and an empty
  string is a present member with an empty value. The two produce different bytes and
  therefore different digests.

### 3. No normalisation

Unicode is **not** normalised. NFC and NFD spellings of the same rendered text are
different evidence and must produce different digests. Normalising would let a
substitution pass verification because it looked the same to a human.

### 4. Integrity binding

For an audit entry:

```
H(canonical(AuditEntry without integrity hash))
```

and never `H(canonical(AuditEntry))` where the latter already carries the result. The
digest is **SHA-256**, rendered lowercase hex.

The rule is enforced by construction, not by remembering to delete a member:
`AuditEntry.canonical_representation()` has no integrity member to omit, and
`core.chain.seal()` attaches the digest outside that representation. A verifier
recomputes by dropping `entry_hash` and canonicalising what remains.

### 5. Confidence

Confidence is carried as an **integer count of basis points** — ten-thousandths — so
that it is an integer under §2:

```
0.0 -> 0        0.5 -> 5000        0.95 -> 9500        1.0 -> 10000
```

Conversion goes through `Decimal(repr(float(v)))` and quantises with ROUND_HALF_EVEN.
Naive binary scaling is wrong for 573 of the 10001 representable inputs — `0.0003 *
10000` is `2.9999999999999996` — so the conversion is specified rather than left to the
arithmetic. Non-finite and out-of-range values are **rejected, never clamped**: a
clamped confidence would be sealed into evidence as though the producer had supplied it.

### 6. Determinism boundary (OQ-6, for M0)

Bit-determinism is **required** of: the canonical encoder, the entry digest, the chain
linkage, the policy-document digest, and the verifier's classification. Sources of
non-determinism are eliminated at the boundary — map iteration order by explicit member
sorting, floating point by exclusion, locale by fixing UTF-8, time and entropy by taking
no part in canonicalisation. Timestamps are recorded input, in a single spelling
(RFC 3339 UTC to the second, `Z`), never read from a clock during canonicalisation.

## Alternatives considered

- **A pipe-delimited or otherwise custom encoding.** Rejected on two grounds. It would
  have to define its own escaping to stay injective, which is exactly the error-prone
  part; and with the corpus unreachable, matching any prior delimiter-based format would
  be reverse-engineering an unavailable specification from inference — which
  `governance/GENESIS.md` §9 forbids.
- **Plain RFC 8785, unrestricted.** Rejected: it admits floats and nulls, which
  reintroduces ECMAScript number formatting and collapses the `None` / `Some("")`
  distinction that M0 must preserve.
- **CBOR / DAG-CBOR canonical form.** A reasonable choice, and more compact. Rejected
  for M0 because the canonical bytes would not be human-readable, and P0-02 requires
  vectors a reviewer can read rather than only re-run.
- **Normalising Unicode to NFC before hashing.** Rejected: see §3.
- **Confidence as a fixed-point string.** Rejected: it re-admits a formatting decision
  (trailing zeros, sign) into the canonical form. An integer has one spelling.

## Consequences

- **No compatibility claim is made or implied** with any prior Aura implementation.
  Establishing byte-compatibility would require the frozen corpus, which is unreachable;
  until it is, any such claim would be an inference. OQ-8 remains open.
- The vectors in `conformance/vectors/` are the contract. Any change to the encoder, the
  member set, the ordering, or the confidence scale changes those bytes and is a
  breaking change requiring a new canonical form identifier and a superseding ADR.
- Integers only means every future real-valued quantity must arrive with a declared
  scale. This is a deliberate, recurring cost.
- SHA-256 is not agile: replacing it is a new canonical form, not a parameter.
- The seal establishes **integrity, not authenticity**. M0 defines no signature scheme
  (`core/signing/README.md`), so a party able to rewrite the whole chain can produce a
  self-consistent package. `tests/mutation/` asserts this limit explicitly so it cannot
  be quietly overclaimed.
