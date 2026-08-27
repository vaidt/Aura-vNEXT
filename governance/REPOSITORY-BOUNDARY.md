# AURA vNEXT — REPOSITORY BOUNDARY

- **Document status:** NORMATIVE
- **Established:** 2026-08-27

## 1. The boundary

There are two sides and they are not symmetric.

| | **SOURCE CORPUS** | **TARGET CANONICAL** |
| --- | --- | --- |
| Repositories | the `Aura-IDToken` repositories | `vaidt/Aura-vNEXT` |
| Status | **FROZEN** | active |
| Writable from here | **NO** | yes |
| Git history flows | **never** into the target | begins at this repository's first commit |
| Authority | none by existence | established by recorded decision |

Aura vNEXT is **not** a fork, mirror, migration, or Git merge of the frozen repositories.

## 2. Prohibited actions

The following are prohibited without exception:

1. Modifying, rewriting, cleaning up, rebasing, force-pushing, or otherwise altering any
   frozen source repository.
2. Importing, grafting, replaying, subtree-merging, or `git filter`-ing the source Git
   history into this repository.
3. Adding a frozen repository as a Git remote, submodule, or subtree of this repository.
4. Copying source repository structure into this repository because it is the existing
   structure.
5. Treating an artifact as canonical because it exists in the source corpus.
6. Deleting, truncating, or "tidying" evidence obtained from the corpus.

## 3. Permitted uses of the frozen corpus

The frozen corpus may be used as:

- a **reference corpus** — read to understand prior intent;
- a **historical record** — cited for what was decided and when;
- a **source of potentially reusable implementation** — subject to §4;
- a **source of specifications**;
- a **source of tests and fixtures**;
- a **source of evidence**;
- a **source of architectural decisions**.

All such use is **read-only** and must be cited by immutable reference (repository, path,
commit SHA) per `provenance/PROVENANCE-POLICY.md`.

## 4. The only route in

An artifact from the corpus may enter Aura vNEXT **only** through the transfer process:

```
DISCOVERED -> UNDER_REVIEW -> VERIFIED -> TRANSFER_APPROVED -> TRANSFERRED
```

with `REJECTED`, `SUPERSEDED`, `RETAIN_REFERENCE_ONLY`, `BLOCKED`, and `CONFLICT` as
terminal or holding states. The process is defined in
`governance/MODULE-ACCEPTANCE-CRITERIA.md` and recorded in
`provenance/transfer-register.json`.

There is no other route. A commit that adds corpus-derived material without a
corresponding register entry in state `TRANSFER_APPROVED` or later is a boundary
violation and must be reverted, not amended over.

## 5. Boundary violations

A boundary violation is not a style problem. On detection:

1. Stop the affected work.
2. Do **not** rewrite history to conceal it. Record it.
3. Open a register entry (or update the existing one) to state `BLOCKED` with the reason.
4. Record the incident in `provenance/BOUNDARY-INCIDENTS.md`.
5. Revert the offending change on the branch it landed on.

## 6. Reachability of the corpus

As of Genesis the frozen corpus is **not reachable** from the build environment. The
transfer register is therefore structurally complete and factually empty: there are zero
`DISCOVERED` artifacts because no artifact has been observed, not because none exist.

Populating the register requires read access to the corpus. See
`provenance/CORPUS-INDEX.md`.
