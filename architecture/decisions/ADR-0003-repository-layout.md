# ADR-0003 — Repository layout is reserved by domain, populated only on demand

- **Status:** ACCEPTED
- **Date:** 2026-08-27

## Context

Genesis must establish a layout without implementing a product, and without replicating the
frozen corpus's structure — which ADR-0001 explicitly declines to inherit.

Two failure modes are in tension:

- **Scaffolding.** Creating packages, interfaces, base classes, and configuration for an
  architecture that has not been decided. This produces abstractions with no concrete
  requirement and quietly fixes design decisions nobody made.
- **No shape at all.** An empty repository gives the first implementer nowhere obvious to
  put anything, and the layout ends up decided by whoever commits first.

## Decision

Establish top-level directories **by domain**, each holding only a `README.md` that states
its purpose and the gate governing what may be placed in it. No source files, no package
manifests, no interfaces, no placeholder types.

```
architecture/   architecture records, decisions, product direction
governance/     genesis, boundary, acceptance criteria, development rules
provenance/     provenance policy, transfer register, per-module records
conformance/    conformance suites and normative test vectors
core/           canonical domain model and core semantics
runtime/        execution / enforcement runtime
policy/         policy representation, compilation, evaluation
audit/          append-only audit chain
evidence/       evidence construction, packaging, verification
integrations/   agent and platform integrations
packs/          policy and governance packs
cli/            verification and operator CLI
tests/          repository-level and cross-cutting tests
tools/          repository tooling used by CI
docs/           product and operator documentation
```

The boundaries follow the governed chain in `architecture/PRODUCT-DIRECTION.md`
(CONTEXT → DECISION → ACTION → OUTPUT → AUDIT → EVIDENCE → VERIFICATION), which is the
one structural commitment Genesis does make.

A `README.md` per directory is not a placeholder: it is the record of what the directory is
for, and Git cannot track an empty directory in any case.

**No primary implementation language is chosen.** That is an open question
(`governance/OPEN-QUESTIONS.md` OQ-2) requiring its own ADR. The Genesis tooling is Python
purely because it must run somewhere with no dependencies; it is not a language decision
and does not bind `core/`, `runtime/`, or any other domain.

## Consequences

- A first implementer has an obvious destination without inheriting a design.
- Directory purposes will need revision as the architecture is decided. Revising a README
  is cheap; unwinding scaffolding is not.
- `tools/validate_structure.py` asserts every reserved directory exists and carries a
  README, so the layout cannot silently erode.
- A directory that stays empty for a long time is evidence the domain boundary was wrong.
  That is a useful signal, and removing an unused reserved directory is a legitimate
  amendment to this ADR.
