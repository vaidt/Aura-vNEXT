# AURA-vNEXT M0 — execution evidence record
Date: 2026-10-24 (UTC)
Repository: `vaidt/Aura-vNEXT`

## Primary run — exact target SHA

- Target branch: `claude/aura-vnext-genesis-xerti8`
- Target/source SHA: `bdec831c165b3a5465bc25f325ed801558cbf81a`
- Workflow run: [#47 / 40052165496](https://github.com/vaidt/Aura-vNEXT/actions/runs/40052165496)
- Event: `push`
- Control branch at run time: `ops/manual-dispatch-m0-baseline-20261024`, created from the target SHA. The run's recorded `head_sha` is exactly the target SHA.
- Job: `governance invariants and M0 gates` (job ID `120746994496`)
- Status/conclusion: `completed / success`
- Created: `2026-10-24T01:58:16Z`; last updated after completion: `2026-10-24T01:58:46Z`
- Attempt: `1`
- Raw full job transcript: [aura-vnext-run-40052165496.log](./aura-vnext-run-40052165496.log)

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
| 9 | Product loop end to end | SUCCESS | 3 application events; generated package matches reference; `aura package` exit 0 with 27-line description; `VERIFIED`, `TAMPERED`, `INVALID` cases pass |
| 10 | Verify the reference evidence package | SUCCESS | `Result: VERIFIED` |
| 11 | Post Run actions/setup-python@v5 | SUCCESS | Cleanup completed |
| 12 | Post Run actions/checkout@v4 | SUCCESS | Cleanup completed |
| 13 | Complete job | SUCCESS | Job completed |

### Product-loop details

- Producer: separate `aura record` CLI processes create the package from three application events.
- Package ID: `aura-evidence-loan-001`; entry count: `3`; chain head: `4c24fc4871ace52f73ae6c9e108c9f06ee7c8ee1eddc958eba352dc945576739`.
- `reproduces reference -> yes`: the generated package's declared producer files match the accepted reference package byte for byte.
- Inspection: `aura package -> exit 0, 27 line description`.
- Pristine package: `VERIFIED`; CLI exit code `0`.
- Mutated package (recorded decision `DENY -> ALLOW` with outer manifest repaired): `TAMPERED`; CLI exit code `2`; clean-room verdict `TAMPERED`.
- Malformed manifest: `INVALID`; CLI exit code `3`; clean-room verdict `INVALID`.
- Clean verifier environment without the producer: `VERIFIED`.
- Both the independent-verification check and product-loop check report `RESULT: PASS -- VERIFIED / TAMPERED / INVALID all reproduced in isolation`.

## Secondary run — workflow configuration only

- Run: [#48 / 40052172827](https://github.com/vaidt/Aura-vNEXT/actions/runs/40052172827)
- SHA: `f15bc39bb9dc79c9c3425c4f52bc387f83b67fd9`
- Job ID: `120747016165`
- Result: `completed / success`; full suite `462 tests`, `OK`; all three classifications reproduced.
- This is a separate operational run, not the primary exact-SHA record.
- Commit comparison with the target SHA shows exactly one file changed: `.github/workflows/baseline.yml`, `+1/-0` (`workflow_dispatch:`). No application code was changed.
- Raw full job transcript: [aura-vnext-run-40052172827.log](./aura-vnext-run-40052172827.log)

## Evidence boundary

This is fresh GitHub Actions evidence that the M0 baseline and product-loop checks passed against source SHA `bdec831c165b3a5465bc25f325ed801558cbf81a`, including `aura record`, `aura package`, and negative integrity classifications `TAMPERED` and `INVALID`.

The run records one GitHub-hosted Linux environment with Python 3.11; it is not cross-platform replay evidence. It does not by itself establish production readiness, cross-repository integration, or any governance ratification beyond the workflow's declared checks.

The report and two complete text transcripts are stored on branch `ops/manual-dispatch-m0-baseline-20261024`; they have not been merged into the default branch.
