# audit — append-only audit chain

**Status: RESERVED. No implementation admitted.**

## Purpose

The tamper-evident, append-only record of the governed chain.

The audit chain's value is that its integrity can be demonstrated to someone who does not
trust the runtime that wrote it. Anything that weakens that property is a defect, not a
trade-off.

## What may be placed here

- the append-only record structure and its integrity mechanism
- chaining, sealing, and integrity verification
- ingestion of records emitted by `runtime/`

Not: evidence packaging (`evidence/`), reporting, or transport-specific storage backends.

Depends on decisions OQ-7 (canonical serialisation and hashing) and OQ-6 (determinism).

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
