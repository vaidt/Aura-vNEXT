# core — canonical domain model and core semantics

**Status: M0 IMPLEMENTATION ADMITTED (ADR-0006 §4).**

## Purpose

The canonical definitions on which everything else depends: the domain model,
identifiers, canonical forms, and the core semantics of the governed chain.

## What is here

| Package | Purpose |
| --- | --- |
| [`canonical/`](canonical/) | `AURA-CANON/1` — the canonical byte form (ADR-0005) |
| [`models/`](models/) | The M0 evidence domain: decisions, violations, audit entries, confidence |
| [`chain/`](chain/) | Entry digests and chain linkage |
| [`policy/`](policy/) | Binding a policy document into the chain — **binding, not evaluation** |
| [`signing/`](signing/) | Deliberately unpopulated: M0 defines no signature scheme |

The contract these implement is `docs/contract/M0-EVIDENCE-CONTRACT.md`. The normative
vectors are `conformance/vectors/m0-canonical-vectors.json`; those vectors, not this
code, are the contract.

## Gate

Changing the canonical encoder, the protected member set, the ordering rules, the
confidence scale, or the digest is a **breaking change**: it requires a new canonical
form identifier and a superseding ADR (contract §9). Regenerating the vectors to make a
test pass inverts the gate.

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later. Nothing here does: M0 is
new implementation written against ADR-0005.
