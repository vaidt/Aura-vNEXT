# SOURCE CORPUS / PROVENANCE POLICY

- **Document status:** NORMATIVE
- **Established:** 2026-08-27

## 1. Principle

> **A clean Git history must not mean loss of provenance.**

Aura vNEXT starts with an independent Git history. That independence removes the *source
repository's* history from this repository; it must not remove the *knowledge of origin*
of anything this repository contains.

Provenance is therefore recorded **in content**, not inferred from Git.

## 2. What must be recorded

For every artifact transferred from the frozen corpus, the following fields are
**mandatory** and are stored in the register entry
(`provenance/transfer-register.json`) and in the per-module record
(`provenance/records/<id>.md`):

| Field | Meaning |
| --- | --- |
| `source_repository` | full repository identifier of the frozen source |
| `source_path` | path within that repository |
| `source_ref` | branch or tag observed |
| `source_commit` | **immutable** commit SHA the artifact was read at |
| `source_version` | released version, where the artifact carries one; `null` otherwise |
| `original_tests` | source paths of the tests that covered the artifact |
| `required_fixtures` | source paths of fixtures, vectors, and golden files required |
| `dependencies` | direct dependencies, internal and external |
| `verification_status` | outcome of verification against the acceptance criteria |
| `transfer_decision` | the recorded decision authorising transfer, and by whom |
| `target_path` | where the artifact lives in this repository |
| `target_commit` | the vNEXT commit that introduced it |

`source_commit` is not optional and is never replaced by a branch name. A branch moves; a
commit does not.

## 3. Provenance of things that are not code

The same policy applies to specifications, test vectors, fixtures, diagrams, threat
models, and prose. A normative sentence copied from the corpus into a vNEXT specification
carries provenance exactly as an implementation module does.

## 4. Derivation, not just copying

Most transfers will be **derivations**, not verbatim copies. The register records the
relationship explicitly via `derivation`:

- `VERBATIM` — byte-identical to the source artifact;
- `ADAPTED` — recognisably the source artifact with recorded modifications;
- `REIMPLEMENTED` — written afresh against the source as specification/evidence;
- `SPECIFICATION_ONLY` — no source code entered; only the specification informed the work.

`ADAPTED` and `REIMPLEMENTED` require the modifications or the behavioural delta to be
stated in the per-module record. "Cleaned up" is not a description of a modification.

## 5. Citing the corpus without transferring

Reading the corpus is unrestricted. Citing it is encouraged. A citation that does not
result in transferred material still uses immutable references:

```
Aura-IDToken/<repo>@<commit>:<path>#L<start>-L<end>
```

An artifact that is useful only as a citation is registered with status
`RETAIN_REFERENCE_ONLY`. That status is a real outcome, not a failure.

## 6. Provenance is append-only

Register entries and per-module records are **append-only in substance**:

- a status may advance or move to a terminal state, and the transition is recorded with a
  date and reason in the entry's `history`;
- a factual error may be corrected, with the correction recorded — not silently overwritten;
- an entry is **never deleted**, including for `REJECTED` and `CONFLICT` outcomes. What was
  rejected, and why, is part of the record.

## 7. Integrity

Where an artifact's byte-level identity matters — test vectors, fixtures, golden files,
evidence samples — the register records `source_sha256` of the source bytes. This allows a
later reader to confirm they are looking at the same artifact without access to the
original repository state.

## 8. Unresolved provenance blocks transfer

If any mandatory field cannot be established — most commonly `source_commit` for an
artifact obtained outside version control — the entry is set to `BLOCKED` and the transfer
stops. Provenance is not reconstructed by inference, and "it must have come from" is not a
provenance record.
