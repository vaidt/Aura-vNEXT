# ADR-0002 — The transfer register is checked data, not prose

- **Status:** ACCEPTED
- **Date:** 2026-08-27

## Context

ADR-0001 makes selective verified transfer the only route from the frozen corpus into
vNEXT. That route is only as strong as its enforcement.

A register kept as a Markdown table is readable but unenforceable: fields drift, statuses
advance without reasons, "approved" appears without a decision, and nothing prevents a
commit from adding legacy code with no entry at all. The failure mode is not malice — it is
that under delivery pressure, unchecked process is silently skipped and later looks like it
was followed.

## Decision

The register is **machine-readable data with a schema and a CI-enforced validator**:

- `provenance/transfer-register.json` — the register.
- `provenance/transfer-register.schema.json` — JSON Schema (draft 2020-12) for its shape.
- `tools/validate_register.py` — enforces the shape **and** the conditional rules that a
  schema cannot express, listed in `provenance/TRANSFER-REGISTER.md` §4.
- `provenance/TRANSFER-REGISTER.md` — prose defining what the data means. Prose explains;
  data is checked.

The validator is written against the **Python 3.11 standard library only**, including its
own schema checking. Genesis has no package manifest and no dependency policy, and adding a
dependency to enforce a governance rule would be a decision taken by convenience rather
than by record.

The validator enforces, in particular, that approval cannot be reached by buildability:
`TRANSFER_APPROVED` requires every applicable criterion resolved, an immutable
`source_commit`, and a named decision.

## Alternatives considered

- **Markdown table.** Rejected: unenforceable, per Context.
- **YAML.** Rejected for Genesis: requires a third-party parser, which the paragraph above
  rules out. Revisit if a dependency policy is established.
- **Git trailers / commit metadata.** Rejected: not reviewable as a whole, and provenance
  must survive independently of Git per `provenance/PROVENANCE-POLICY.md` §1.
- **A full JSON Schema library.** Rejected for Genesis on the dependency grounds above; the
  schema file remains standard and portable, so a library can validate it later without
  changing the data.

## Consequences

- Register edits are hand-written JSON. Slightly awkward; acceptable given entries are
  rare and deliberate.
- The validator duplicates a subset of JSON Schema semantics. It covers only the
  constructs this schema uses; if the schema grows beyond them, the validator must grow
  with it or be replaced by a library under a recorded dependency policy.
- Every rule in `TRANSFER-REGISTER.md` §4 must have a corresponding check. A documented
  rule with no check is a gap, and `tests/test_register.py` asserts the validator rejects
  the cases it claims to reject.
