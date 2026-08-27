# policy — policy representation, compilation, and evaluation

**Status: RESERVED. No implementation admitted.**

## Purpose

How policy is expressed, validated, compiled, versioned, and evaluated to a decision.

Policy semantics are defined in exactly one place. Duplicating them into `runtime/` or an
integration is prohibited by `governance/DEVELOPMENT-RULES.md` §5.

## What may be placed here

- policy representation and its schema
- validation and compilation
- the evaluator producing DECISION from CONTEXT
- policy versioning and identity, so a decision can name the policy that produced it

Not: enforcement mechanics, packs (see `packs/`), or storage.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
