# runtime — execution and enforcement runtime

**Status: RESERVED. No implementation admitted.**

## Purpose

The component that sits in the execution path of an agent and enforces decisions at
runtime — governing CONTEXT, ACTION, and OUTPUT as they occur, and emitting the records
that `audit/` and `evidence/` depend on.

The runtime enforces decisions; it does not define what they mean. Policy meaning lives in
`policy/` and `core/`.

## What may be placed here

- interception and enforcement points
- context, action, and output governance at execution time
- emission of audit records
- replay execution, once decided (OQ-6)

Not: policy semantics, evidence format definitions, or product integrations.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
