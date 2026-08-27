# packs — policy and governance packs

**Status: RESERVED. No implementation admitted.**

## Purpose

Distributable, versioned bundles of policy and governance content — the shipped
counterpart to the mechanism in `policy/`.

A pack is content, not code. A pack that needs code to work indicates a missing capability
in `policy/`.

## What may be placed here

- versioned policy packs and their manifests
- governance packs mapping controls to policy
- pack-level tests and conformance fixtures

Packs are versioned and identifiable, so a decision can name the pack version that
produced it.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
