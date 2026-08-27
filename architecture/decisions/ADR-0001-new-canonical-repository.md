# ADR-0001 — Aura vNEXT is a new repository with independent canonical history

- **Status:** ACCEPTED
- **Date:** 2026-08-27
- **Supersedes:** —
- **Superseded by:** —

## Context

Aura exists today as the `Aura-IDToken` repositories. Those repositories are being frozen.
A new canonical implementation, Aura vNEXT, is to be built.

Three approaches were available:

1. **Continue in place** — keep developing the existing repositories.
2. **Fork / migrate** — copy the repositories, import their Git history, and refactor
   forward.
3. **New repository with selective verified transfer** — start an independent history and
   admit artifacts from the old corpus only after verification.

The problem the decision has to solve is not code volume. It is **authority**. In the
existing corpus, an artifact's presence is indistinguishable from its endorsement: code,
documentation, comments, prior AI conclusions, branch names, and commit messages all carry
the same apparent weight, and none of them is traceable to a specification or a decision.
Aura's product direction — evidence, provenance, replay, verification — cannot be built on
a base whose own provenance is unestablished.

## Decision

**Aura vNEXT is a new repository with a new and independent Git history.**

Specifically:

1. The Git history of the frozen repositories is **not** imported, grafted, replayed,
   subtree-merged, or filtered into vNEXT. vNEXT's history begins at its own first commit.
2. The frozen repositories are **read-only reference corpus** and are never modified,
   rebased, force-pushed, or cleaned up.
3. No frozen repository is added as a remote, submodule, or subtree of vNEXT.
4. Artifacts enter vNEXT only through the transfer process defined in
   `governance/MODULE-ACCEPTANCE-CRITERIA.md`, recorded in
   `provenance/transfer-register.json`.
5. The old repository structure is **not** replicated by default. vNEXT's layout is chosen
   for vNEXT (see ADR-0003).
6. Provenance is preserved **in content** rather than in Git, per
   `provenance/PROVENANCE-POLICY.md`.

## Rationale

- **Independent history forces authority to be re-established.** With no inherited
  history, nothing is canonical by inertia. Every artifact must justify its presence once.
- **A clean history is not the goal; a verified base is.** Independence is the mechanism,
  verification is the objective. Hence the register: independence without a provenance
  record would trade one untraceable base for another.
- **Freezing the source protects the evidence.** The corpus is the historical record of
  what was decided and built. Refactoring it in place would destroy the very evidence the
  new product depends on.
- **The alternative approaches fail on the actual problem.** Continuing in place preserves
  the authority ambiguity. Forking preserves it and adds the illusion of a fresh start:
  imported history makes legacy code look reviewed, and it is precisely the review that is
  missing.

## Consequences

**Accepted costs**

- Bootstrapping cost is real. Nothing is available until it is verified; early velocity is
  low by construction.
- Per-artifact verification is expensive, and much of the corpus will end as
  `RETAIN_REFERENCE_ONLY` or `REJECTED`.
- `git log` and `git blame` in vNEXT will not reach pre-Genesis work. This is intended;
  the compensating mechanism is the provenance record, which must therefore be maintained
  with discipline rather than treated as paperwork.
- Genuinely good legacy code will be re-verified and sometimes re-implemented. Accepted.

**Obligations created**

- The transfer register and per-module records must be maintained, or the decision's
  compensating mechanism fails and provenance is lost for real.
- CI must enforce the register's invariants mechanically. Documented process that is not
  checked will drift.
- Corpus access is required before any transfer work can begin (see
  `provenance/CORPUS-INDEX.md`).

## Compliance

Enforced by `tools/validate_register.py` and `tools/validate_structure.py`, run by
`tests/` and by `.github/workflows/baseline.yml`.

A commit adding corpus-derived material without a register entry at `TRANSFER_APPROVED` or
later is a boundary violation under `governance/REPOSITORY-BOUNDARY.md` §5 and is reverted,
not amended over.
