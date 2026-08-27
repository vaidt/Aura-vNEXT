# MODULE ACCEPTANCE CRITERIA

- **Document status:** NORMATIVE
- **Established:** 2026-08-27

## 1. Scope

These criteria gate the admission of any artifact from the frozen `Aura-IDToken` corpus
into Aura vNEXT. They apply to implementation modules, specifications, tests, fixtures,
and evidence artifacts alike, with the per-class adjustments in §4.

> **A module is not approved because it builds.**
> Buildability is one criterion among many, and it is the weakest of them.

## 2. Lifecycle

```
DISCOVERED ──▶ UNDER_REVIEW ──▶ VERIFIED ──▶ TRANSFER_APPROVED ──▶ TRANSFERRED
                   │                │               │
                   ├────────────────┴───────────────┴──▶ REJECTED
                   ├──▶ SUPERSEDED
                   ├──▶ RETAIN_REFERENCE_ONLY
                   ├──▶ BLOCKED        (resumable: reason must be recorded)
                   └──▶ CONFLICT       (resumable: requires a decision)
```

| Status | Meaning |
| --- | --- |
| `DISCOVERED` | Observed in the corpus and recorded. No claim of any kind is made about it. |
| `UNDER_REVIEW` | Actively being assessed against §3. |
| `VERIFIED` | All applicable criteria in §3 are satisfied and the evidence is recorded. |
| `TRANSFER_APPROVED` | Verified **and** a recorded decision authorises transfer. |
| `TRANSFERRED` | Present in vNEXT at a recorded `target_path` and `target_commit`. |
| `REJECTED` | Will not be transferred. The reason is recorded and the entry is retained. |
| `SUPERSEDED` | Replaced by a different artifact or a new vNEXT implementation. The successor is named. |
| `RETAIN_REFERENCE_ONLY` | Valuable as reference or evidence; not admitted as implementation. |
| `BLOCKED` | Assessment cannot proceed. The blocker is named and is actionable. |
| `CONFLICT` | Two or more candidate authorities disagree. Requires an architectural decision. |

Only `TRANSFER_APPROVED` and `TRANSFERRED` permit corpus-derived material to exist in this
repository. `VERIFIED` alone does **not**.

`BLOCKED` and `CONFLICT` are not failures — they are the correct outcome when the
alternative would be a guess.

## 3. Criteria

An artifact reaches `VERIFIED` only when every applicable criterion below is satisfied and
the supporting evidence is recorded in `provenance/records/<id>.md`.

### C1 — Known provenance
Every mandatory field of `provenance/PROVENANCE-POLICY.md` §2 is established, including an
immutable `source_commit`. Unestablished provenance ⇒ `BLOCKED`.

### C2 — Known dependencies
The complete direct dependency set is enumerated: internal modules, external packages with
versions, runtime services, and implicit environmental dependencies (clock, filesystem,
network, entropy, locale). An unenumerated dependency ⇒ not verified.

### C3 — Completeness
The artifact is whole: no missing files, no references to code that was not located, no
truncated specification, no fixture referenced but absent. A partial artifact is
`BLOCKED`, never "transferred with gaps".

### C4 — Buildability
The artifact compiles/loads in the vNEXT toolchain, or the specific work required to make
it do so is recorded and bounded. **Necessary, never sufficient.**

### C5 — Test coverage
The original tests are identified, are transferred with the artifact, and pass against it
in vNEXT. Where the original tests are absent or inadequate, the gap is stated explicitly
and the tests required are written **before** `TRANSFER_APPROVED` — not scheduled after it.
Tests are never weakened, skipped, or narrowed to obtain a pass.

### C6 — Deterministic behaviour where required
For any artifact whose outputs feed policy decisions, the audit chain, evidence, or replay:
identical inputs must produce identical outputs. Sources of non-determinism (map/set
iteration order, floating point, time, entropy, locale, concurrency) are identified and
either eliminated or explicitly made part of the recorded input. Undetermined determinism
⇒ not verified.

### C7 — Conformance
The artifact's behaviour matches the governing specification, demonstrated against
conformance vectors held in `conformance/`. Where no governing specification is
identified, the artifact cannot be verified for conformance ⇒ `BLOCKED` on the
specification, or `CONFLICT` if candidate specifications disagree.

### C8 — Security considerations
Cryptographic primitives, key handling, trust boundaries, input validation, serialisation
and deserialisation, and error paths that could leak state are reviewed and the review is
recorded. Cryptographic and evidence-integrity code additionally requires known-answer
tests against recorded vectors.

### C9 — Absence of unresolved semantic conflict
No conflict with an existing vNEXT definition, a governing specification, or another
in-flight transfer. Policy semantics are defined in exactly one place; a transfer that
would duplicate them is rejected or the duplication is resolved first. Unresolved ⇒
`CONFLICT`.

### C10 — Licence and rights
The artifact's licensing and ownership permit its use here, including any third-party code
it embeds or vendors. Unclear rights ⇒ `BLOCKED`.

### C11 — No proprietary third-party material
The artifact contains no implementation, architecture, terminology, or proprietary
material derived from a competitor product. Competitive analysis informs requirements; it
never enters the implementation.

## 4. Per-class application

| Class | Criteria applied |
| --- | --- |
| Implementation module | C1–C11 |
| Specification / normative text | C1, C3, C7, C9, C10, C11 |
| Tests | C1, C2, C3, C4, C6, C10 |
| Fixtures / conformance vectors | C1, C3, C6, C10 — plus `source_sha256` |
| Evidence artifacts | C1, C3, C8, C10 — retained byte-exact |

A criterion recorded as "not applicable" states why. Silence is not a waiver.

## 5. Approval

`VERIFIED` is a technical finding; `TRANSFER_APPROVED` is a decision. They are recorded
separately and are never asserted in the same act by the same reasoning.

Transfer approval requires:

1. all applicable criteria `VERIFIED` with recorded evidence, **and**
2. a decision recorded in the entry's `transfer_decision`, naming the deciding authority
   and the date, **and**
3. no open `CONFLICT` on any artifact this one depends on.

Where transfer would change protocol semantics, normative requirements, governance
boundaries, the authority hierarchy, a compliance claim, a canonical mathematical
definition, or a public API contract, an **architecture decision record is required
first**.

## 6. Post-transfer

On reaching `TRANSFERRED`:

- `target_path` and `target_commit` are recorded;
- the per-module record in `provenance/records/` is complete;
- the transferred tests run in CI like any other vNEXT test;
- the artifact is thereafter governed as vNEXT code. Its corpus origin is history, not
  standing authority, and it may be changed only by the ordinary rules in
  `governance/DEVELOPMENT-RULES.md`.
