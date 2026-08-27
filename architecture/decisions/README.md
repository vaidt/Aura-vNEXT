# Architecture Decision Records

An ADR records a decision that has been **taken**, the context that forced it, and the
consequences accepted. It is not a proposal and not a design document.

## Index

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-0001](ADR-0001-new-canonical-repository.md) | Aura vNEXT is a new repository with independent canonical history | ACCEPTED |
| [ADR-0002](ADR-0002-transfer-register-as-checked-data.md) | The transfer register is checked data, not prose | ACCEPTED |
| [ADR-0003](ADR-0003-repository-layout.md) | Repository layout is reserved by domain, populated only on demand | ACCEPTED |

## When an ADR is required

Before implementation, for any change to:

- protocol semantics,
- normative requirements,
- governance boundaries,
- the authority hierarchy,
- compliance claims,
- canonical mathematical definitions,
- public API contracts,
- the transfer or provenance mechanism itself,
- scope beyond what is already decided.

If you are unsure whether a change needs an ADR, it needs an ADR.

## Rules

- Numbers are sequential and never reused.
- An accepted ADR is not edited to change its decision. It is superseded by a new ADR, and
  both records are updated with `Supersedes` / `Superseded by`.
- Correcting a typo or a broken link is fine. Rewriting the rationale after the fact is not.
- Add every new ADR to the index above; `tests/test_structure.py` checks that the index and
  the directory agree.

## Format

```
# ADR-NNNN — <decision, stated as an outcome>

- **Status:** PROPOSED | ACCEPTED | SUPERSEDED
- **Date:** YYYY-MM-DD
- **Supersedes:** / **Superseded by:**

## Context      — the forces, and the problem the decision must actually solve
## Decision     — what was decided, concretely enough to be checked
## Alternatives considered   — and why they were not chosen
## Consequences — what this costs, and what obligations it creates
```
