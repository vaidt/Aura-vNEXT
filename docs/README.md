# docs — product and operator documentation

**Status: RESERVED for implementation. Operator documentation admitted.**

No implementation module lives here, and none may. What does live here is the
documentation an operator needs to run M0 — [`OPERATING-M0.md`](OPERATING-M0.md) — and
the normative contract it serves. Both are documentation, which is what this directory
is for; neither establishes authority beyond the decisions it cites.

## Purpose

Documentation for users, operators, and integrators.

Documentation describes what exists. It does not establish authority: a statement here is
not normative unless it cites the specification, ADR, or decision that makes it so
(`governance/GENESIS.md` §5).

## What may be placed here

- product and concept documentation
- operator and integration guides
- glossary and reference material

Governance and architecture records do **not** live here — they live in `governance/`,
`architecture/`, and `provenance/`.

## Gate

Nothing may be placed here that derives from the frozen `Aura-IDToken` corpus unless it
has a transfer register entry at `TRANSFER_APPROVED` or later
(`provenance/transfer-register.json`).

New work written here still requires the decisions it depends on to exist first. See
`governance/DEVELOPMENT-RULES.md` §4 and `governance/OPEN-QUESTIONS.md`.

No primary implementation language has been chosen (OQ-2).

## Contents

| Document | Status | Purpose |
| --- | --- | --- |
| [`OPERATING-M0.md`](OPERATING-M0.md) | OPERATOR GUIDE | How to operate M0: the workflow, the three results, exit statuses, error handling, and what Aura does not claim. Non-normative; the contract governs. |
| [`contract/M0-EVIDENCE-CONTRACT.md`](contract/M0-EVIDENCE-CONTRACT.md) | NORMATIVE | The M0 evidence contract: canonical form, digest, package, verifier |
| [`GENESIS-STATE.md`](GENESIS-STATE.md) | FACTUAL RECORD | The repository's state at the Genesis commit, and what was observed |
