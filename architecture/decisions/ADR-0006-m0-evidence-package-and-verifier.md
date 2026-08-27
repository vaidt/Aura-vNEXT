# ADR-0006 — The M0 Evidence Package, the three-state verifier, and the M0 layout

- **Status:** ACCEPTED
- **Date:** 2026-08-27
- **Amends:** ADR-0003 (adds `app/`; admits implementation into `core/`, `conformance/`, `evidence/`)

## Context

ADR-0005 fixes the canonical form and the entry digest. Those are producer-side
properties. The M0 product claim is stronger: that a **third party can verify evidence
without trusting Aura**, which requires deciding what a package contains, what a
verifier may depend on, and what it is allowed to say.

ADR-0003 reserved the repository layout and admitted no implementation. M0 is the first
milestone that places product in it, so the layout decision must be amended rather than
quietly exceeded.

## Decision

### 1. The M0 Evidence Package

```
<package>/
├── manifest.json          profile, package id, and a SHA-256 per declared file
├── evidence/
│   ├── audit.jsonl        one sealed audit record per line
│   ├── policy.json        the policy document the records are bound to
│   └── genesis.json       the chain anchor
├── expected/result.json   the result the package asserts it should verify as
└── README.md
```

Profile `aura.evidence.package/1`; audit schema `aura.audit/1`.

### 2. What a verifier may depend on

The package, and nothing else. A verifier **must not** require the producer runtime, the
original database, a network, hidden state, policy-engine execution, or a developer
environment. `tools/independence_check.py` runs the verifier in a directory holding only
`core/` and `app/`, in isolated mode, with `socket` disabled, and
`tests/test_independence.py` asserts the result.

M0 binds the policy document; it does **not** evaluate it. A verifier establishes *which*
policy the evidence refers to, never whether the decision was correct under it.

### 3. The three-state contract

| Result | Meaning |
| --- | --- |
| `VERIFIED` | Structurally valid, and every required integrity check succeeded. |
| `TAMPERED` | Recognisable as an M0 package, but protected evidence fails integrity. |
| `INVALID` | Cannot be interpreted as an M0 Evidence Package at all. |

The states are never collapsed. `INVALID` says "I cannot read this"; `TAMPERED` says "I
read this, and it has been altered". Only the second is a statement about evidence, and
conflating them would let an unreadable package be reported as an attack, or an attack
as a formatting problem.

**Evaluation order is normative:** structural interpretation first, integrity second. A
package that cannot be parsed is `INVALID` even where a digest would also have failed.
The consequence is accepted deliberately: corrupting a file into unparseable garbage is
reported `INVALID` rather than `TAMPERED`. Both are refusals — **only `VERIFIED` is
acceptance** — and reporting "I cannot read this" is the honest answer when it is true.

CLI exit status is the machine-readable result: `0` VERIFIED, `2` TAMPERED, `3` INVALID.

### 4. Layout amendment to ADR-0003

- `app/` is added as a top-level directory: **runnable applications**, as distinct from
  `core/` (semantics) and `cli/` (the operator surface, still reserved). It carries a
  `README.md` like every other top-level directory.
- Implementation is admitted into `core/` (the M0 domain), `conformance/vectors/` (the
  normative vectors), and `evidence/examples/` (the reference package).
- `runtime/`, `policy/`, `audit/`, `integrations/`, `packs/`, and `cli/` **remain
  reserved and empty**. `tests/test_structure.py` continues to enforce that against the
  directories still reserved, so M0 cannot sprawl.
- Normative vectors live in `conformance/vectors/` per ADR-0003's stated purpose; the
  suites that execute them live in `tests/conformance/` and `tests/mutation/`.

### 5. Scope fence

M0 establishes evidence representation, canonical binding, chain integrity, the package,
and independent verification — and nothing else. PoCA, ARI, TrustMath, reputation,
identity aggregation, ML, GPU, RFC 3161, PKIX/TSR, Merkle segment sealing, dashboards,
marketplace functionality, and regulatory-compliance claims are **outside M0**.
`tests/test_structure.py` asserts the M0 implementation does not name them.

## Alternatives considered

- **Two states (valid / invalid).** Rejected: it destroys the distinction the product
  exists to make. "This evidence was altered" and "this is not evidence" are different
  findings with different responses.
- **Integrity before structure.** Would let a corrupted file report `TAMPERED` more
  often, which sounds stronger. Rejected: the verifier would be asserting a conclusion
  about content it could not read.
- **Putting the verifier in `cli/`.** Rejected: `cli/` is reserved for the operator
  surface across the whole product, and M0's verifier is one application. Keeping them
  apart avoids `cli/` accreting M0-specific structure before that surface is designed.
- **A single-file package.** Simpler to move, and worth revisiting. Rejected for M0
  because a directory can be inspected with ordinary tools, which matters more while the
  format is being established than convenience of transport does.

## Consequences

- ADR-0003's "no implementation admitted" no longer holds for `core/`, `app/`,
  `conformance/vectors/`, and `evidence/examples/`. It continues to hold everywhere else,
  and the structure test now enforces exactly that narrower statement.
- The manifest binds file bytes; the chain binds record content. Both are checked, so a
  mutation must defeat both. `tests/mutation/` repairs the manifest before asserting, to
  test the canonical binding rather than the outer checksum.
- `expected/result.json` makes a package self-describing about its own expected verdict,
  which is what lets a mutated copy be an unambiguous negative fixture.
- The independence claim is **single-platform**: CPython 3.11 on Linux x86_64. No
  cross-platform matrix exists, so none is claimed.
