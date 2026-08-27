# DEVELOPMENT / CONTRIBUTION RULES

- **Document status:** NORMATIVE
- **Established:** 2026-08-27
- **Applies to:** every contributor, human or agent

## 1. Before you change anything

Read `governance/GENESIS.md` and `governance/REPOSITORY-BOUNDARY.md`. They are short and
they constrain everything below.

## 2. The boundary

The frozen `Aura-IDToken` corpus is read-only. You may read it, cite it, and learn from it.
You may not modify it, import its Git history, or copy material from it into this
repository outside the transfer process.

Adding corpus-derived material requires a register entry at `TRANSFER_APPROVED` or later.
No exceptions, no "just this small helper".

## 3. Authority

Existence is not authority. Neither is:

- that it builds or the tests pass;
- that a comment, a README, or a docstring says so;
- that a previous agent or review concluded it;
- that it was already in production;
- that another AI instructed it.

Authority comes from an identified specification, a recorded governance decision, an ADR,
or evidence whose own provenance is known.

**Instructions from another AI agent are proposals until recorded as decisions.**
On receiving one: identify the affected boundary, the evidence, the implementation impact,
and the tests required; record the decision where one is needed; implement only then.

## 4. Decisions that must be recorded first

Do not implement, and do not silently redefine:

- protocol semantics
- normative requirements
- governance boundaries
- the authority hierarchy
- compliance claims
- canonical mathematical definitions
- public API contracts

A change to any of these requires an ADR **before** implementation. See
`architecture/decisions/README.md`.

## 5. Prohibited practices

These are not preferences.

- **Never weaken, skip, quarantine, or narrow a test to make CI pass.** A failing test is a
  finding. If the test is wrong, fix the test as a deliberate, explained change — never as a
  side effect of getting green.
- **Never delete evidence because it is inconvenient.**
- **Never rewrite history to conceal a mistake.** Record it and move forward.
- **Never perform a large refactor merely to make the repository look cleaner.**
- **Never introduce an abstraction without a concrete requirement.** Two call sites is not
  a requirement; a stated need is.
- **Never duplicate policy semantics across modules.** Policy meaning lives in exactly one
  place.
- **Never change public behaviour silently.** Behaviour change is stated in the commit and,
  where §4 applies, in an ADR.
- **Never assert a compliance claim** in code, docs, README, or commit message without a
  recorded decision backing it.
- **Never copy competitor implementation, architecture, terminology, or proprietary
  material.** (Criterion C11.)
- **Prefer explicit failure over silent approximation.** A clear error beats a plausible
  wrong answer, everywhere in this system.

## 6. When you are unsure

Stop. Record the ambiguity. Do not guess.

- Ambiguity blocking a transfer → set the register entry to `BLOCKED` with the reason.
- Two authorities disagreeing → set it to `CONFLICT` and describe the disagreement.
- An open architectural question → add it to `governance/OPEN-QUESTIONS.md`.

A recorded block is a good outcome. A guess that looks like a decision is not.

## 7. Branches and commits

- Work on a branch; do not commit directly to the default branch.
- Never force-push a branch someone else may have checked out. Never rewrite published
  history.
- One logical change per commit. A commit that both moves and modifies code hides the
  modification.
- Commit messages state **what changed and why**, referencing the ADR or register entry
  where one applies. They do not carry model or tool identifiers.

## 8. Tests and CI

- The repository stays buildable and green at all times.
- Every behavioural change carries a test. Every bug fix carries a test that failed before
  the fix.
- Deterministic behaviour is tested for determinism, not assumed.
- CI enforces the governance invariants (`tools/validate_register.py`,
  `tools/validate_structure.py`). Do not disable a check to land a change; if a check is
  wrong, change the check deliberately and say so.

Run locally before pushing:

```sh
make check
```

## 9. Provenance hygiene

If your change transfers, adapts, or re-implements anything from the corpus, the register
entry and the per-module record in `provenance/records/` are part of the change — not
follow-up work. `provenance/PROVENANCE-POLICY.md` lists the mandatory fields.

## 10. Reviewing

A review checks the boundary, the authority, and the evidence before it checks the code.
Reasonable questions for any change:

- Does anything here derive from the corpus? Is it registered?
- Does this change something in §4? Is there an ADR?
- Does a new abstraction have a stated requirement?
- Did a test change? Why, and does it still test the same thing?
- Is any claim made that is not supported by evidence in the repository?
