# AURA-vNEXT M0 — execution evidence record
Date: 2026-10-24 (UTC)
Repository: `vaidt/Aura-vNEXT`

## Primary run — exact target SHA

- Target branch: `claude/aura-vnext-genesis-xerti8`
- Target/source SHA: `bdec831c165b3a5465bc25f325ed801558cbf81a`
- Workflow run: [#47 / 40052165496](https://github.com/vaidt/Aura-vNEXT/actions/runs/40052165496)
- Event: `push`
- Control branch: `ops/manual-dispatch-m0-baseline-20261024` was created at the target SHA; this run's recorded `head_sha` is exactly the target SHA.
- Job: `governance invariants and M0 gates` (job ID `120746994496`)
- Status/conclusion: `completed / success`
- Started: `2026-10-24T01:58:16Z`
- Completed (last observed updated_at): `2026-10-24T01:58:46Z`
- Attempt: `1`
- Raw job transcript: [aura-vnext-run-40052165496.log](./aura-vnext-run-40052165496.log)

### All job steps

| # | Step | Result | Recorded output / note |
|---:|---|---|---|
| 1 | Set up job | SUCCESS | Completed |
| 2 | Run actions/checkout@v4 | SUCCESS | Checkout completed |
| 3 | Run actions/setup-python@v5 | SUCCESS | Python 3.11 setup completed |
| 4 | Validate repository structure | SUCCESS | `tools/validate_structure.py` exited successfully |
| 5 | Validate module transfer register | SUCCESS | `tools/validate_register.py` exited successfully |
| 6 | Check M0 conformance fixtures for drift | SUCCESS | `m0 fixtures: OK -- 6 file(s) match the implementation` |
| 7 | Run the full test suite | SUCCESS | `Ran 462 tests in 19.390s`; `OK` |
| 8 | Independent verification | SUCCESS | `VERIFIED`, `TAMPERED`, `INVALID` reproduced in isolation; `RESULT: PASS` |
| 9 | Product loop end to end | SUCCESS | Event → package → `VERIFIED`; mutated package → `TAMPERED`; malformed package → `INVALID`; `RESULT: PASS` |
| 10 | Verify the reference evidence package | SUCCESS | `Result: VERIFIED` |
| 11 | Post Run actions/setup-python@v5 | SUCCESS | Cleanup completed |
| 12 | Post Run actions/checkout@v4 | SUCCESS | Cleanup completed |
| 13 | Complete job | SUCCESS | Job completed |

### Negative and positive classification results

- Pristine package: `VERIFIED`; CLI exit code `0`.
- Mutated package: `TAMPERED`; CLI exit code `2`; independent/clean-room verdict `TAMPERED`.
- Malformed manifest/package: `INVALID`; CLI exit code `3`; independent/clean-room verdict `INVALID`.
- Independence check: all three statuses reproduced in an isolated verifier environment.
- Product loop: recorded a fresh event, generated a package, then verified the generated package independently. All three classifications passed.

## Secondary run — workflow configuration only

- Run: [#48 / 40052172827](https://github.com/vaidt/Aura-vNEXT/actions/runs/40052172827)
- SHA: `f15bc39bb9dc79c9c3425c4f52bc387f83b67fd9`
- Job ID: `120747016165`
- Result: `completed / success`; full test suite: `462 tests`, `OK`; three classifications reproduced.
- This is a separate operational run, not the primary exact-SHA record.
- Commit comparison confirms a single-file delta from the target SHA: `.github/workflows/baseline.yml`, one addition (`workflow_dispatch:`), zero deletions. No application code changed.
- Raw transcript: [aura-vnext-run-40052172827.log](./aura-vnext-run-40052172827.log)

## Evidence boundary

This establishes a fresh successful M0 baseline execution for source SHA `bdec831c165b3a5465bc25f325ed801558cbf81a` in GitHub Actions, including package generation/verification and negative classifications `TAMPERED` and `INVALID`. It does not by itself establish production readiness, cross-repository integration, or any governance ratification beyond the workflow's declared checks.
