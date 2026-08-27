# cli — verification and operator CLI

**Status: RESERVED. No implementation admitted.**

## Purpose

The command-line surface: verifying evidence, inspecting the audit chain, and operating
the system.

The verification commands are part of the product's external claim — a third party uses
them to check an evidence artifact — so their behaviour is a public contract and changes to
it require an ADR.

## What may be placed here

- evidence verification commands
- audit chain inspection
- operator and diagnostic commands

Not: policy semantics, evidence format definitions, or business logic of any kind. The CLI
calls the libraries; it does not contain a second implementation.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
