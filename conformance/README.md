# conformance — conformance suites and normative test vectors

**Status: RESERVED. No implementation admitted.**

## Purpose

Executable conformance suites and the normative vectors an implementation must satisfy.

Criterion C7 requires conformance to be demonstrated against material held here. A
specification with no vectors here cannot be used to verify anything.

## What may be placed here

- normative test vectors, with recorded provenance and `source_sha256`
- conformance suites executing those vectors
- known-answer tests for cryptographic and evidence-integrity code (C8)

Vectors transferred from the corpus are retained **byte-exact**. A vector that is
"adjusted to match the implementation" is not a vector.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).
