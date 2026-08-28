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

**The schema is a closed world.** A verifier validates presence and type of every member
above, and every violation member, **before canonical hashing**. A record that is missing
a required member, carries a member of the wrong type, or carries **any member not named
here** is `INVALID`: it is not an audit entry. M0 defines no extension mechanism and no
forward-compatible schema negotiation — an unknown member cannot be ignored, because an
ignored member is excluded from the preimage, which would let a record carrying
undeclared content reach `VERIFIED`.

**Value domains are enforced too, and separately.** A verifier checks, in order:

1. **structural interpretability** — presence, type, closed world, supported schema;
2. **the semantic AuditEntry domain** — the value domains in the table above: the closed
   decision vocabulary, the single timestamp spelling, 64 lowercase hex for every digest
   (`policy_hash`, `input_hash`, `prev_hash`, `shadow_hash` when present, and
   `entry_hash`), a non-negative `seq`, non-empty `request_id`, `schema`, and violation
   `rule` and `action`, and `confidence` in `[0, 10000]`;
3. **integrity** — canonical bytes, SHA-256, chain linkage, policy binding.

Layers 1 and 2 both decide whether the record is an M0 AuditEntry at all, so both yield
`INVALID`. Only layer 3 yields `TAMPERED`, and only for a record that is already a valid
AuditEntry whose protected content no longer matches its committed binding.

**Being hashable is not being interpretable.** A record carrying `decision =
"WHATEVER"` can be canonicalised, sealed with a correct digest, linked into a chain and
listed in a repaired manifest — and would then present as intact evidence for a decision
M0 does not define. It is refused before it is hashed.

Replacing a value with *another value inside the domain* — one defined decision for
another, one well-formed digest for another — leaves a valid AuditEntry, so that remains
a **mutation** and classifies as `TAMPERED`. `policy_repr` has no value constraint and
may be empty.

On the wire a sealed record additionally carries `entry_hash` (string, required), which
is the integrity value and is not part of the canonical representation (§5).

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
- **Lone surrogates are rejected.** A surrogate code point (U+D800–U+DFFF) has no UTF-8
  encoding and therefore no canonical byte form. It raises a canonicalisation error at
  the boundary, which a verifier reports as `INVALID`. It must never surface as an
  implementation-level encoding error escaping the boundary.

### 3.1 Worked example

One entry, spelled out end to end, so the canonical bytes and the digest can be derived
from this document without reading any implementation.

**Input.** The audit entry with `seq` 0, `request_id` `req-0001`, `timestamp`
`2026-08-27T10:00:00Z`, `decision` `DENY`, `policy_hash` sixty-four `a`, `input_hash`
sixty-four `b`, `prev_hash` sixty-four `0`, `policy_repr` `loan.underwriting/2`, `schema`
`aura.audit/1`, empty `violations`, empty `metadata`, and **no** `shadow_hash`.

**Applying §3.** Twelve members are present; `shadow_hash` is unset so it contributes no
member at all. Member names are ASCII here, so UTF-16 order is plain alphabetical:
`decision`, `input_hash`, `metadata`, `policy_hash`, `policy_repr`, `prev_hash`,
`request_id`, `schema`, `seq`, `timestamp`, `violations`. No character in any value
requires escaping. `seq` is an integer and is emitted as `0`. There is no whitespace.

**Canonical bytes** (416 bytes, UTF-8):

```
{"decision":"DENY","input_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","metadata":{},"policy_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","policy_repr":"loan.underwriting/2","prev_hash":"0000000000000000000000000000000000000000000000000000000000000000","request_id":"req-0001","schema":"aura.audit/1","seq":0,"timestamp":"2026-08-27T10:00:00Z","violations":[]}
```

**SHA-256 of those bytes** — reproducible with any SHA-256 implementation, for example
`printf '%s' '<the line above>' | sha256sum`:

```
a57453c0b46266c0c8f7528f08f7fa350f3ce77a058ee309a4e943e366acf6ef
```

This is the `minimal` vector in `conformance/vectors/m0-canonical-vectors.json`.
`tests/conformance/test_independent_oracle.py` asserts the document and the vector do not
drift apart: if they ever did, this section would have stopped being a specification.

### 3.2 Member ordering, concretely

UTF-16 code-unit order is not code-point order, and the difference is reachable. Given
member names `zkey`, `🔐key` (U+1F510), and `�key` (U+FFFD):

| Name | First UTF-16 unit | First code point |
| --- | --- | --- |
| `zkey` | U+007A | U+007A |
| `🔐key` | U+D83D (lead surrogate) | U+1F510 |
| `�key` | U+FFFD | U+FFFD |

AURA-CANON/1 orders them `zkey`, `🔐key`, `�key`, because U+D83D < U+FFFD. Sorting by
code point would order them `zkey`, `�key`, `🔐key`. An implementation that sorts
native strings in a language whose strings are sequences of code points — Python, Go,
Rust — will get this wrong unless it converts to UTF-16 units first. This is the
`unicode-astral` vector.

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

**Chain terminus.** `prev_hash` binds the chain only *backwards*. The final record has
nothing linking forward from it, and the links alone say nothing about how many records
there should be — so without a further binding the tail could be rewritten and resealed,
or records dropped from the end, with every surviving link still consistent. The manifest
therefore commits to both ends:

| Declaration | Meaning |
| --- | --- |
| `chain_head` | the `entry_hash` of the **final** AuditEntry in the package |
| `entry_count` | the exact number of AuditEntry records in `evidence/audit.jsonl` |

`chain_head` is the final record's own `entry_hash`. It is **not** a digest of the file
and introduces **no new hashing domain**; the AuditEntry canonical domain is unchanged.

A verifier checks both *after* verifying the chain, and reaches `VERIFIED` only if
`len(records) == entry_count` and `records[-1].entry_hash == chain_head`.

## 6. The Evidence Package

```
<package>/
├── manifest.json          profile, package id, SHA-256 per declared file
├── evidence/
│   ├── audit.jsonl        one sealed record per line
│   ├── policy.json        the policy document the records are bound to
│   └── genesis.json       the chain anchor
├── expected/result.json   NON-NORMATIVE fixture metadata (see 6.1)
└── README.md
```

The manifest declares the **verification contract** the package requires, and a verifier
must check each declaration against what it implements rather than merely confirming the
field is present:

| Declaration | Supported value |
| --- | --- |
| `profile` | `aura.evidence.package/1` |
| `audit_schema` | `aura.audit/1` |
| `canonical_form` | `AURA-CANON/1` |
| `digest` | `SHA-256` |

It also declares the chain terminus, `chain_head` and `entry_count` (§5). These are
checked against the parsed chain rather than against a fixed supported value, so their
classification differs: a **malformed or missing** declaration is `INVALID` — the
manifest cannot be interpreted — while a **well-formed declaration that disagrees with
the evidence** is `TAMPERED`, because the package is recognisable and its evidence no
longer matches what it committed to.

A missing or unsupported declaration is `INVALID`. A package asking for a canonical form
or digest this build does not implement is asking for a verification it cannot perform,
and saying so is the only honest answer.

### 6.1 Declared paths must stay inside the package

The manifest travels with the evidence and is **untrusted input**. Each key in
`files` is an instruction about which file to read, so a verifier must guarantee that
no declared path escapes the package root — otherwise the claim below, that a verifier
depends on the package and nothing else, is simply false.

A declared path is accepted only if **all** of the following hold:

- it is a **relative POSIX path** — not absolute, no backslash separator;
- it contains **no `..` component**;
- it is in **canonical form** — no `.` segment, no repeated separator, no trailing
  separator. Refused rather than normalised, because `files` is a digest map keyed by
  these strings: two spellings of one file would be two entries free to declare two
  different digests for the same bytes;
- its **resolved** target lies strictly inside the **resolved** package root. This is
  the check that catches a package-local symlink whose target leaves the package.
  Containment, not a ban on symlinks: a link resolving inside the package is fine.

The check runs **before any file is read**, so an escaping path never reaches a digest.

A path outside the package makes the package **`INVALID`, not `TAMPERED`**. Tampering
means recognisable evidence that fails its cryptographic binding; a package directing
the verifier to read outside itself is not an M0 Evidence Package at all.

Note the trap this closes: `Path(root) / "../outside"` stays lexically inside but
resolves out, and `Path(root) / "/etc/passwd"` discards the root entirely and yields
`/etc/passwd`. Joining is not containment.

### 6.2 `expected/result.json` is non-normative

`expected/result.json` is **test fixture metadata**. It is **not** part of the protected
evidence and **not** part of the verification contract.

- The verifier **never reads it**. The verdict is derived from the evidence alone.
- It is **not** listed among the required files, and it is **not** bound by the
  manifest's digest set. Altering or deleting it cannot change any verdict.
- It exists so a fixture can state what it is expected to verify as, which is what lets
  a mutated copy serve as an unambiguous negative fixture in the test suite.

A verifier that trusted this file could be told what to conclude by the package it is
examining. `tests/conformance/` asserts the verifier ignores it — including when the
file claims a verdict that contradicts the evidence.

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

It does **not** establish **authenticity or authorship**. M0 defines no signature scheme
(`core/signing/README.md`), and the manifest is unsigned, so a party willing to rewrite
the chain *and* restate the manifest's declared terminus still produces a self-consistent
package that verifies. `tests/conformance/test_chain_terminus.py` asserts this remaining
limit explicitly, so it cannot be quietly overclaimed.

State the limit accurately. The terminus binding (§5) raises the cost of a forgery from
**one record** — before it, rewriting the tail alone, or simply deleting records from the
end, produced a package that verified — to the whole chain plus the manifest. It does not
eliminate that forgery. What `VERIFIED` means is: *this package is internally consistent
with the evidence it declares and binds.* It says nothing about who produced it. Any
document stating or implying that M0 proves origin is wrong.

## 8. Conformance vectors — what they are and are not

`conformance/vectors/m0-canonical-vectors.json` records, for every fixture:

```
INPUT  ->  EXPECTED CANONICAL BYTES  ->  EXPECTED SHA-256
```

The bytes are recorded twice — as UTF-8 text and as hex — so the recording is unambiguous
and a reviewer can read it rather than only re-run it. Exposing the bytes is the point:
a vector set that recorded only digests would pass against an encoder wrong in a way the
fixtures happened not to reach, and would give a second implementer nothing to diff.

The vectors are **produced** by this implementation (`tools/build_m0_fixtures.py`) and
are **cross-checked against three oracles that are not this implementation**
(`tests/conformance/test_independent_oracle.py`):

1. **CPython's own `json` encoder.** For the restricted AURA-CANON/1 domain,
   `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` reproduces
   19 of the 20 vectors byte for byte. The twentieth is `unicode-astral`, where the
   §3.2 ordering rule is exactly what diverges; the suite asserts that divergence is
   present and is **ordering alone** — same members, same values.
2. **A second implementation written from this document** rather than from the code
   (`tests/conformance/_contract_oracle.py`), which derives UTF-16 code units
   arithmetically instead of via a codec. It reproduces all 20 vectors, including the
   astral case, and the suite asserts it imports nothing from `core/` or `app/`.
3. **An external SHA-256 binary** (`sha256sum` or `openssl`), which confirms all 20
   recorded digests and removes `hashlib` from the trust base.

These are still **not third-party conformance vectors for AURA-CANON/1** — no such suite
exists, because the form is defined here (§0), and no compatibility claim follows from
any of this. What the oracles establish is that the recorded bytes and digests are not
merely whatever this implementation happened to emit: an encoder wrong from the first day
would have to be wrong identically in CPython's encoder, in a separately written
implementation, and in an external digest tool.

The drift check (`tools/build_m0_fixtures.py --check`) runs in CI, so a failing vector
cannot be resolved by regenerating it.

## 9. Changing this contract

The vectors are the contract. Any change to the canonical encoder, the protected member
set, the ordering rules, the confidence scale, or the digest is a **breaking change**:
it requires a new canonical form identifier (`AURA-CANON/2`, `aura.audit/2`) and a
superseding ADR. SHA-256 is not agile — replacing it is a new canonical form, not a
parameter.
