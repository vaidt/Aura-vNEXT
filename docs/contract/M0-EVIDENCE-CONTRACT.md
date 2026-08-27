# M0 EVIDENCE CONTRACT

- **Document status:** NORMATIVE
- **Established:** 2026-08-27
- **Decided by:** ADR-0004, ADR-0005, ADR-0006
- **Canonical form:** `AURA-CANON/1` · **Audit schema:** `aura.audit/1` · **Package profile:** `aura.evidence.package/1`

## 0. Provenance of this contract — read first

This contract is **defined in this repository**. It was not recovered from, derived from,
or checked against any prior Aura implementation.

At the time of writing, the frozen `Aura-IDToken` corpus is **not reachable** from this
environment (`provenance/CORPUS-INDEX.md` §2), and `governance/REPOSITORY-BOUNDARY.md`
forbids reaching for it. The transfer register holds **zero** entries. No governing
specification, conformance vector, or normative text describing a prior Aura canonical
form exists here.

Two consequences follow, and neither may be softened in later documents:

1. **No compatibility claim.** Nothing in M0 claims byte-compatibility, digest
   compatibility, or format compatibility with any deployed Aura product. Establishing
   such a claim requires the corpus. Until then it would be an inference, which
   `governance/GENESIS.md` §9 forbids. This is tracked as **OQ-8**.
2. **Authority is the gate, not the ancestry.** Per `governance/GENESIS.md` §5, this
   contract's authority is ADR-0005 and ADR-0006 together with the vectors in
   `conformance/vectors/` — not resemblance to anything prior.

## 1. Scope

M0 establishes exactly five things:

1. evidence representation,
2. canonical cryptographic binding,
3. chain integrity,
4. the portable Evidence Package,
5. independent verification.

Everything else is out of scope. ADR-0006 §5 enumerates the exclusions; they are not
restated here, so that the list has one home.

## 2. The audit entry

Every member below is **protected**: it participates in the digest, and altering any of
them is detectable.

| Member | Type | Required | Notes |
| --- | --- | --- | --- |
| `schema` | string | yes | `aura.audit/1` |
| `seq` | integer | yes | 0-based position in the chain |
| `request_id` | string | yes | non-empty |
| `timestamp` | string | yes | RFC 3339 UTC to the second, `Z` only |
| `decision` | string | yes | `ALLOW`, `DENY`, or `REQUIRE_APPROVAL` |
| `policy_hash` | string | yes | 64 lowercase hex |
| `policy_repr` | string | yes | may be empty |
| `input_hash` | string | yes | 64 lowercase hex |
| `prev_hash` | string | yes | 64 lowercase hex; the genesis anchor for `seq` 0 |
| `violations` | array | yes | **ordered**; may be empty |
| `metadata` | object | yes | string→string; may be empty |
| `shadow_hash` | string | **optional** | 64 lowercase hex; **absent member when unset** |

A violation is `{ "rule": string, "action": string, "confidence": integer }`, all three
protected. **Violation order is protected**: reordering is a mutation.

`timestamp` is recorded input. No clock is read during canonicalisation.

## 3. The canonical form — AURA-CANON/1

A restricted profile of **RFC 8785 (JSON Canonicalization Scheme)**:

- UTF-8 output, no insignificant whitespace;
- members sorted by **UTF-16 code-unit sequence** of their names — not code-point order,
  which differs above the BMP;
- strings escaped per RFC 8785 §3.2.2.2: `\"`, `\\`, the short forms `\b \t \n \f \r`,
  and `\u00xx` for the remaining C0 controls; every other character emitted literally;
- **integers only** — floating point is not representable;
- **no null** — an unset optional value is an **absent member**.

Two further rules:

- **`None` ≠ `Some("")`.** Absence changes the member set; an empty string is a present
  member with an empty value. Different bytes, therefore different digests.
- **No Unicode normalisation.** NFC and NFD spellings of the same rendered text are
  different evidence. Normalising would let a substitution pass because it looked the
  same to a human.

## 4. Confidence

Confidence is an integer count of **basis points** (ten-thousandths):

```
0.0 -> 0        0.5 -> 5000        0.95 -> 9500        1.0 -> 10000
```

Conversion runs through `Decimal(repr(float(v)))`, quantised ROUND_HALF_EVEN. Naive
binary scaling is wrong for 573 of the 10001 representable inputs (`0.0003 * 10000` is
`2.9999999999999996`), so the conversion is specified rather than left to the arithmetic.

Non-finite and out-of-range values are **rejected, never clamped**. A clamped confidence
would be sealed into evidence as though the producer had supplied it.

## 5. The integrity binding

```
entry_hash = SHA-256( AURA-CANON/1( entry without the integrity hash ) )
```

and **never** `SHA-256(canonical(entry))` where the latter already carries the result.

The rule holds by construction: the protected representation has no integrity member to
omit, and the digest is attached outside it. A verifier recomputes by dropping
`entry_hash` and canonicalising what remains.

**Chain.** `prev_hash` of entry *n* is the `entry_hash` of entry *n−1*; entry 0 uses the
package's genesis anchor. Linking uses the **claimed** digest of the predecessor, so a
tampered entry cannot re-link the chain around itself.

## 6. The Evidence Package

```
<package>/
├── manifest.json          profile, package id, SHA-256 per declared file
├── evidence/
│   ├── audit.jsonl        one sealed record per line
│   ├── policy.json        the policy document the records are bound to
│   └── genesis.json       the chain anchor
├── expected/result.json   the verdict the package asserts about itself
└── README.md
```

A verifier depends on the package and nothing else: not the producer runtime, the
original database, a network, hidden state, policy-engine execution, or a developer
environment.

M0 **binds** the policy document; it does not **evaluate** it. A verifier establishes
which policy the evidence refers to, never whether the decision was correct under it.

## 7. The three-state verifier

| Result | Meaning |
| --- | --- |
| `VERIFIED` | Structurally valid, and every required integrity check succeeded. |
| `TAMPERED` | Recognisable as an M0 package, but protected evidence fails integrity. |
| `INVALID` | Cannot be interpreted as an M0 Evidence Package at all. |

Never collapsed. Evaluation order is **structure first, integrity second**: a package
that cannot be parsed is `INVALID` even where a digest would also have failed. Both
`TAMPERED` and `INVALID` are refusals — **only `VERIFIED` is acceptance**.

CLI exit status: `0` VERIFIED, `2` TAMPERED, `3` INVALID.

### What VERIFIED does and does not establish

`VERIFIED` establishes **integrity**: the evidence is internally consistent and has not
been altered since it was sealed.

It does **not** establish **authenticity**. M0 defines no signature scheme
(`core/signing/README.md`), so a party able to rewrite every record and the manifest can
produce a self-consistent package. `tests/mutation/` asserts this limit explicitly, so it
cannot be quietly overclaimed. Any document stating or implying that M0 proves origin is
wrong.

## 8. Conformance vectors — what they are and are not

`conformance/vectors/m0-canonical-vectors.json` records, for every fixture:

```
INPUT  ->  EXPECTED CANONICAL BYTES  ->  EXPECTED SHA-256
```

The bytes are recorded twice — as UTF-8 text and as hex — so the recording is unambiguous
and a reviewer can read it rather than only re-run it. Exposing the bytes is the point:
a vector set that recorded only digests would pass against an encoder wrong in a way the
fixtures happened not to reach, and would give a second implementer nothing to diff.

**These are known-answer tests generated by this implementation** (by
`tools/build_m0_fixtures.py`). They lock the format against silent regression: any change
to the encoder, member set, ordering, or confidence scale changes the recorded bytes and
fails the suite. They are **not** independent third-party vectors, and they do not prove
the format is correct against an external authority — no such authority is reachable
(§0). What they prove is that the format is *fixed*, *stated*, and *reproducible*.

## 9. Changing this contract

The vectors are the contract. Any change to the canonical encoder, the protected member
set, the ordering rules, the confidence scale, or the digest is a **breaking change**:
it requires a new canonical form identifier (`AURA-CANON/2`, `aura.audit/2`) and a
superseding ADR. SHA-256 is not agile — replacing it is a new canonical form, not a
parameter.
