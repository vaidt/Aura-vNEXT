# integrations — agent and platform integrations

**Status: RESERVED. No implementation admitted.**

## Purpose

Adapters connecting Aura to agent frameworks, platforms, and host environments.

An integration adapts; it never re-implements. It must not contain policy semantics, its
own copy of a canonical definition, or a second interpretation of the governed chain.

## What may be placed here

- framework and platform adapters
- transport and protocol bindings
- integration-specific configuration and its tests

Each integration is expected to be independently buildable and testable.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
