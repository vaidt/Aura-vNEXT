# aura-evidence-loan-001 — reference M0 Evidence Package

A minimal, complete, reproducible Evidence Package. It exists to be verified by someone
who has none of the machinery that produced it.

It is **produced, not hand-written**: `tools/build_m0_fixtures.py` builds it by calling
`app.producer` — the same code path `aura record` uses — so this package is an example of
what the product emits rather than a fixture that merely resembles one.

## Verify it

```sh
python3 -m app.aura verify evidence/examples/aura-evidence-loan-001
```

Expected: `VERIFIED`. Exit status `0`. The package states this about itself in
[`expected/result.json`](expected/result.json).

To verify it the way a third party would — in a directory holding only `core/` and
`app/verifier/`, in isolated mode, with the network disabled and the producer absent:

```sh
python3 tools/independence_check.py
```

To reproduce this package from the application events it records, and watch the whole
loop run with the producer and the verifier in separate environments:

```sh
python3 tools/product_loop_check.py
```

## Contents

| Path | What it is |
| --- | --- |
| `manifest.json` | Profile, package id, and a SHA-256 for every declared file |
| `evidence/audit.jsonl` | Three chained audit records, one per line, each sealed |
| `evidence/policy.json` | The policy document every record is bound to |
| `evidence/genesis.json` | The chain anchor for record 0 |
| `expected/result.json` | The verdict this package asserts about itself |

The three records model one loan decision: intake (`ALLOW`), assessment
(`REQUIRE_APPROVAL`, two violations), and settlement (`DENY`). Record 2 carries a
metadata value that is the empty string, so the package itself exercises the
`None` / `Some("")` distinction; record 1's note contains a quote, a pipe, and a
backslash.

## What a VERIFIED result means

That the evidence is **internally consistent and unaltered since it was sealed**.

It does **not** mean the package is authentic. M0 defines no signature scheme, so anyone
able to rewrite every record and the manifest can produce a self-consistent package. See
`docs/contract/M0-EVIDENCE-CONTRACT.md` §7 and `core/signing/README.md`.

## Regenerating

```sh
python3 tools/build_m0_fixtures.py
```

The loan scenario is stated once, as application events, in that script
(`LOAN_POLICY` and `LOAN_EVENTS`); everything protected here — sequence numbers, chain
links, digests, the manifest terminus — is computed from them by `app.producer`.

Regenerate only when the canonical form has genuinely changed — which is a breaking
change requiring a superseding ADR and a new form identifier
(`docs/contract/M0-EVIDENCE-CONTRACT.md` §9), not a way to make a failing test pass.
