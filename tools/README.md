# tools — repository tooling used by CI

**Status: RESERVED. No implementation admitted.**

## Purpose

Scripts that enforce this repository's own invariants.

Genesis tooling is Python 3.11 **standard library only** — no third-party dependencies —
because no dependency policy has been decided (OQ-4, ADR-0002). This is not a language
decision for the product.

## What may be placed here

- `validate_register.py` — transfer register schema and rule enforcement
- `validate_structure.py` — repository structure and ADR index enforcement

A rule documented in governance but not checked here is a gap. Add the check.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
