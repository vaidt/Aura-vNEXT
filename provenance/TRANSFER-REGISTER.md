# MODULE TRANSFER REGISTER

- **Document status:** NORMATIVE
- **Established:** 2026-08-27
- **Register data:** [`provenance/transfer-register.json`](transfer-register.json)
- **Schema:** [`provenance/transfer-register.schema.json`](transfer-register.schema.json)
- **Validator:** [`tools/validate_register.py`](../tools/validate_register.py) — runs in CI

## 1. What the register is

The register is the **single record of every artifact considered for transfer** from the
frozen `Aura-IDToken` corpus into Aura vNEXT — including the ones that were rejected.

It is the mechanism that makes the boundary enforceable. Corpus-derived material may exist
in this repository only if a register entry authorises it.

The register is data, not prose, so that CI can check it. This document defines what the
data means.

## 2. Current state

```
entries            : 0
corpus_reachable   : false
status_at          : 2026-08-27
```

**Zero entries means nothing has been observed, not that nothing exists.** The frozen
corpus was not reachable from the Genesis environment. See
[`provenance/CORPUS-INDEX.md`](CORPUS-INDEX.md) for what is required to begin discovery.

## 3. Entry lifecycle

Statuses and their meanings are defined normatively in
[`governance/MODULE-ACCEPTANCE-CRITERIA.md`](../governance/MODULE-ACCEPTANCE-CRITERIA.md) §2.
Summary:

`DISCOVERED` · `UNDER_REVIEW` · `VERIFIED` · `TRANSFER_APPROVED` · `TRANSFERRED` ·
`REJECTED` · `SUPERSEDED` · `RETAIN_REFERENCE_ONLY` · `BLOCKED` · `CONFLICT`

## 4. Rules the validator enforces

These are checked mechanically on every push. They are not advisory.

1. **Schema.** Every entry conforms to the schema.
2. **Unique, never-reused ids.** Ids match `^[A-Z]{2,6}-[0-9]{4}$` and are unique.
3. **History is present and terminates at the current status.** Every entry has at least
   one history record, and the last record's status equals the entry's status.
4. **Immutable provenance before approval.** `TRANSFER_APPROVED` and `TRANSFERRED` require
   a 40-hex `source_commit`. A branch name is not a commit.
5. **Verification precedes approval.** `TRANSFER_APPROVED` and `TRANSFERRED` require every
   criterion applicable to the artifact class to be `PASS` or `NOT_APPLICABLE`, with a
   non-empty note in both cases. `NOT_ASSESSED` blocks approval.
6. **Approval is a decision.** `TRANSFER_APPROVED` and `TRANSFERRED` require a
   `transfer_decision` naming `decided_by`, `decided_on`, and a `reference`.
7. **Derivation is declared.** `TRANSFER_APPROVED` and `TRANSFERRED` require `derivation`.
8. **Transfer is located.** `TRANSFERRED` requires `target_path` and `target_commit`, and
   `target_path` must exist in the working tree.
9. **Per-module record exists.** `TRANSFERRED` requires `record` to point at an existing
   file under `provenance/records/`.
10. **Fixture and evidence integrity.** `TRANSFERRED` entries of class `FIXTURE` or
    `EVIDENCE` require `source_sha256`.
11. **Terminal states state their reason.** `BLOCKED` requires `blocked_reason`; `CONFLICT`
    requires `conflict_description`; `REJECTED` requires `rejected_reason`; `SUPERSEDED`
    requires `superseded_by`.
12. **Dependencies resolve and do not block.** Every id in `depends_on` exists, and no
    entry may be `TRANSFER_APPROVED` or `TRANSFERRED` while any dependency is `BLOCKED`,
    `CONFLICT`, or `REJECTED`.
13. **No self-dependency.**

Rules 4–7 exist for one reason: **an artifact must never reach approval because it
builds.** Buildability is criterion C4 of eleven.

## 5. Amending the register

- Advance a status by appending to `history` with the date and the reason. Do not edit a
  past history record.
- Never delete an entry. `REJECTED` and `CONFLICT` outcomes are part of the record.
- Correcting a factual error is permitted; append a history record describing the
  correction. Silent overwriting is not permitted.
- Changing `status_at` without reviewing the entries is a false statement about the
  register and is not permitted.

## 6. Adding an entry

Minimal `DISCOVERED` entry:

```json
{
  "id": "TR-0001",
  "title": "<what the artifact is>",
  "artifact_class": "IMPLEMENTATION",
  "status": "DISCOVERED",
  "provenance": {
    "source_repository": "<owner>/<repo>",
    "source_path": "<path/in/source>",
    "source_ref": "<branch-or-tag observed>",
    "source_commit": null
  },
  "criteria": {},
  "history": [
    { "date": "YYYY-MM-DD", "status": "DISCOVERED", "reason": "Observed during corpus survey <n>." }
  ]
}
```

Then run:

```sh
python3 tools/validate_register.py
```

## 7. What the register is not

It is not a backlog, not a plan, and not a statement of intent. An entry does not mean an
artifact will be transferred. `DISCOVERED` makes no claim about the artifact whatsoever.
