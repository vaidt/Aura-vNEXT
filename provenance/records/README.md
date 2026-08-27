# provenance/records/

One record per artifact that reaches `TRANSFERRED`, named `<register-id>.md`
(e.g. `TR-0001.md`). The register holds the structured fields; the record holds the
reasoning, the evidence, and the delta.

**No records exist.** Nothing has been transferred.

## Template

```markdown
# <REGISTER-ID> — <artifact title>

- Register entry: `provenance/transfer-register.json` → `<REGISTER-ID>`
- Status: TRANSFERRED
- Derivation: VERBATIM | ADAPTED | REIMPLEMENTED | SPECIFICATION_ONLY

## Source

| Field | Value |
| --- | --- |
| source_repository | |
| source_path | |
| source_ref | |
| source_commit | (40-hex) |
| source_version | |
| source_sha256 | (fixtures and evidence) |

## Dependencies
Internal, external with versions, and environmental (clock, filesystem, network, entropy,
locale).

## Original tests and fixtures
Source paths, and where they now live in vNEXT.

## Verification
One subsection per applicable criterion C1–C11 with the evidence for its outcome.
A criterion marked NOT_APPLICABLE states why.

## Behavioural delta
For ADAPTED and REIMPLEMENTED: exactly what differs from the source and why.
"Cleaned up" and "modernised" are not descriptions of a change.

## Transfer decision
Decided by, decided on, reference (ADR or governance decision).

## Target
| Field | Value |
| --- | --- |
| target_path | |
| target_commit | |

## Open items
Anything unresolved that a future reader must know. Empty is a valid answer; omitting the
section is not.
```
