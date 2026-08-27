# OPEN ARCHITECTURAL QUESTIONS

- **Document status:** FACTUAL RECORD
- **Last updated:** 2026-08-27

Questions that are **open**. Each is unanswered on purpose: answering it by convenience
would fix a decision nobody has taken. Where an answer is needed before work can proceed,
that work is blocked, not guessed.

A question is closed only by a recorded decision — normally an ADR — and this file then
records the ADR that closed it.

| # | Question | Blocks | Resolution vehicle |
| --- | --- | --- | --- |
| OQ-1 | **Corpus access.** Which repositories constitute the frozen corpus, where are they hosted, at which commits were they frozen, and how does this environment read them? | All discovery and all transfer. Hard blocker for M0. | `provenance/CORPUS-INDEX.md` + access grant |
| OQ-2 | **Primary implementation language and toolchain** for `core/`, `runtime/`, `policy/`, `audit/`, `evidence/`, `cli/`. | First implementation module; dependency policy; CI beyond the governance baseline. | ADR |
| OQ-3 | **Licence and rights model** for Aura vNEXT. No `LICENSE` file has been added, deliberately — a licence is a decision, not a default. | Public contribution; criterion C10 assessment of vNEXT's own output. | Decision by the rights holder, then ADR |
| OQ-4 | **Dependency policy.** What may be depended on, under which licences, and how are dependencies pinned and verified? Genesis tooling is stdlib-only to avoid pre-empting this (ADR-0002). | Any module with external dependencies. | ADR |
| OQ-5 | **Authority hierarchy for governance decisions.** Who decides, and what constitutes a recorded decision, where an ADR is not the vehicle? `transfer_decision.decided_by` currently has no defined value space. | `TRANSFER_APPROVED` on any entry. | Governance decision |
| OQ-6 | **Determinism boundary.** Which components must be bit-deterministic, and under which conditions? Criterion C6 currently says "where required" without defining the required set. | C6 assessment; replay design. | ADR |
| OQ-7 | **Canonical serialisation and hashing.** Which canonical form and which primitives underpin the audit chain and evidence integrity? | Audit chain; evidence format; C8 assessment. | ADR |
| OQ-8 | **Relationship between vNEXT and the deployed Aura-IDToken product.** Is vNEXT a successor, a parallel product, or a re-platform? Does compatibility with existing artifacts constrain it? | Scope of transfer; whether `SUPERSEDED` is the expected outcome for most of the corpus. | Product decision, then ADR |
| OQ-9 | **Release, versioning, and support model.** | Public API contracts; compatibility commitments. | ADR |

## Adding a question

Add a row when you find something unanswerable from the specification, an existing
decision, or evidence. Say what it **blocks** — a question that blocks nothing is not
tracked here.

Do not answer a question by implementing one of its answers.
