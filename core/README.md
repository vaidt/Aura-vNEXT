# core — canonical domain model and core semantics

**Status: RESERVED. No implementation admitted.**

## Purpose

The canonical definitions on which everything else depends: the domain model, identifiers,
canonical forms, and the core semantics of the governed chain.

A definition lives here exactly once. If two modules would each define the same concept,
the concept belongs here and the modules refer to it.

## What may be placed here

- canonical domain types and their invariants
- canonical serialisation forms, once decided (OQ-7)
- core semantics referenced by `policy/`, `runtime/`, `audit/`, and `evidence/`

Not: policy evaluation, transport, storage, or integration concerns.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
