# SOURCE CORPUS INDEX

- **Document status:** FACTUAL RECORD
- **Last verified:** 2026-08-27

## 1. Purpose

An index of the frozen source repositories that constitute the Aura reference corpus:
what they are, where they are, and at which commit each was frozen.

Discovery cannot begin, and no register entry can advance past `DISCOVERED`, until this
index names a repository and an immutable freeze commit for it.

## 2. Current state — CORPUS NOT REACHABLE

As of 2026-08-27 the frozen `Aura-IDToken` corpus is **not reachable** from the environment
that produced the Genesis commit.

Observed facts:

- The build environment's GitHub access is scoped to `vaidt/Aura-vNEXT` only.
- A repository listing filtered on `aura` returned `vaidt/Aura-vNEXT` and nothing else.
- A repository listing filtered on `idtoken` returned no repositories.

This records **absence of access**, not absence of the corpus. No inference is drawn about
whether the corpus exists, where it is hosted, what it contains, or how many repositories
it comprises. Nothing is assumed from the name `Aura-IDToken` beyond its use as an
identifier in this repository's governance documents.

Consequently `provenance/transfer-register.json` carries `"corpus_reachable": false` and
zero entries.

## 3. Index

| # | Repository | Host | Freeze ref | Freeze commit | Verified on | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| — | *(none recorded)* | — | — | — | — | Corpus not reachable; see §2 |

## 4. What is required to populate this index

For each source repository:

1. **Identity** — the exact `owner/repo`, and the host if not GitHub.
2. **Read access** — granted to the working environment. Read-only is sufficient and is
   what should be granted; write access to a frozen repository is a boundary hazard, not a
   convenience.
3. **Freeze point** — the ref and the **40-hex commit SHA** at which the repository was
   frozen. A branch name alone is not a freeze point: a branch can move, and the entire
   provenance model depends on the reference not moving.
4. **Freeze confirmation** — confirmation that the repository is in fact frozen (for
   example, archived or protected), so that a commit recorded here remains its head.
5. **Rights** — licensing and ownership sufficient for criterion C10.

## 5. Rules

- A repository is added here only after items 1–4 of §4 are established. A partially
  established entry is not added "provisionally".
- The freeze commit is recorded as a full 40-character SHA. Never a branch, never a tag
  alone, never an abbreviated SHA.
- If a freeze commit is later found to have moved, the corpus was not frozen. Stop all
  transfer work, record the fact here and in `provenance/BOUNDARY-INCIDENTS.md`, and
  re-establish the freeze point before continuing.
- This index is append-and-correct, never rewritten. A correction states what was wrong.
