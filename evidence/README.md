# evidence — evidence construction, packaging, and verification

**Status: RESERVED. No implementation admitted.**

## Purpose

Turning the audit record into artifacts that a third party can verify **without trusting
Aura** — and the verification procedure itself.

This is the differentiating layer of the product. An evidence artifact that can only be
checked by Aura is not evidence.

## What may be placed here

- evidence artifact formats and their specifications
- construction of evidence packages from the audit chain
- the independent verification procedure
- compliance-oriented evidence artifacts, once authorised

Not: the audit chain itself (`audit/`), the CLI surface (`cli/`), or reporting.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
