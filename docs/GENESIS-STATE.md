# Genesis State Report

- **Document status:** FACTUAL RECORD
- **Date:** 2026-08-27

The state of `vaidt/Aura-vNEXT` at the Genesis commit. Recorded so a later reader can tell
what was established, what was observed, and what was deliberately left undone.

## A. Repository state before Genesis

The repository existed and was **completely empty**: no commits on any branch, no files, no
tags. There was nothing to inspect, migrate, or reconcile.

## B. What Genesis establishes

Process, not product:

- the repository boundary against the frozen corpus,
- the authority model,
- the provenance policy,
- the transfer register, its schema, and its validator,
- the module acceptance criteria,
- three architecture decision records,
- the reserved repository layout,
- a dependency-free CI baseline enforcing the above.

## C. What Genesis does NOT establish

- No implementation of any kind.
- No protocol, policy semantics, evidence format, audit chain, or replay mechanism.
- No transferred artifact. The register holds **zero** entries.
- No primary implementation language (OQ-2), licence (OQ-3), or dependency policy (OQ-4).
- No compliance claim.

## D. Corpus observation

The frozen `Aura-IDToken` corpus was **not reachable** from the Genesis environment.
GitHub access was scoped to `vaidt/Aura-vNEXT`; repository listings filtered on `aura` and
on `idtoken` returned only this repository and nothing, respectively.

This is recorded as absence of access. Nothing is inferred about whether the corpus exists,
where it is hosted, or what it contains. See `provenance/CORPUS-INDEX.md` §2.

## E. Consequence for M0

Discovery cannot begin without corpus access (OQ-1). Until it is granted:

- no register entry can be created,
- no acceptance criterion can be assessed,
- no transfer can be approved.

This is a hard blocker on transfer work specifically. It does not block resolving the
architectural questions in `governance/OPEN-QUESTIONS.md`, several of which (OQ-2, OQ-4,
OQ-5) would otherwise block the first transfer the moment the corpus becomes available.

## F. Verification

```sh
make check
```

Runs the structure validator, the register validator, and 37 governance invariant tests.
All passing at the Genesis commit.
