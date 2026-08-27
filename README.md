# Aura vNEXT

**Status: GENESIS.** This repository contains no product implementation yet.

Aura vNEXT is a **new product** and the **new canonical implementation** of Aura. It is
not a fork, mirror, migration, or Git merge of the frozen `Aura-IDToken` repositories.

## What this repository is right now

Genesis establishes the foundation required before any implementation is admitted:

- the repository boundary between the frozen source corpus and this canonical target,
- the provenance policy that governs how any legacy artifact may enter,
- the transfer register that records every candidate artifact and its status,
- the module acceptance criteria that gate transfer,
- the architecture decision records for the above,
- a minimal CI baseline that enforces these invariants.

No implementation modules have been transferred. No implementation modules are approved
for transfer.

## Intended direction (non-authorizing)

Aura vNEXT is intended to evolve into **Evidence-First Runtime Governance for AI Agents**,
governing the chain:

```
CONTEXT -> DECISION -> ACTION -> OUTPUT -> AUDIT -> EVIDENCE -> VERIFICATION
```

The objective is to establish not merely whether an action was *allowed*, but whether the
resulting execution can be **reconstructed, verified, and supported by evidence**.

See [`architecture/PRODUCT-DIRECTION.md`](architecture/PRODUCT-DIRECTION.md). That document
is explicitly **non-normative**: it describes direction, not authorization to implement.

## Read these first

| Document | Purpose |
| --- | --- |
| [`governance/GENESIS.md`](governance/GENESIS.md) | What Genesis is, what it fixes, what it deliberately leaves open |
| [`governance/REPOSITORY-BOUNDARY.md`](governance/REPOSITORY-BOUNDARY.md) | The non-negotiable boundary against the frozen corpus |
| [`provenance/PROVENANCE-POLICY.md`](provenance/PROVENANCE-POLICY.md) | How provenance is established and preserved |
| [`governance/MODULE-ACCEPTANCE-CRITERIA.md`](governance/MODULE-ACCEPTANCE-CRITERIA.md) | The gate every candidate module must pass |
| [`provenance/TRANSFER-REGISTER.md`](provenance/TRANSFER-REGISTER.md) | The register, its lifecycle, and how to amend it |
| [`governance/DEVELOPMENT-RULES.md`](governance/DEVELOPMENT-RULES.md) | Contribution and development rules |
| [`architecture/decisions/`](architecture/decisions/) | Architecture decision records |

## Repository layout

Directories are **reserved**, not populated. Each carries a `README.md` stating its purpose
and the gate that governs what may be placed in it.

```
architecture/    architecture records, decisions, product direction
governance/      genesis, boundary, acceptance criteria, development rules
provenance/      provenance policy, transfer register, per-module provenance records
conformance/     conformance suites and normative test vectors
core/            canonical domain model and core semantics
runtime/         execution / enforcement runtime
policy/          policy representation, compilation, evaluation
audit/           append-only audit chain
evidence/        evidence construction, packaging, verification
integrations/    agent and platform integrations
packs/           policy and governance packs
cli/             verification and operator CLI
tests/           repository-level and cross-cutting tests
tools/           repository tooling used by CI
docs/            product and operator documentation
```

## Baseline checks

The Genesis baseline is dependency-free (Python 3.11 standard library only):

```sh
make check
```

or directly:

```sh
python3 -m unittest discover -s tests -v
```

## Boundary reminder

The `Aura-IDToken` repositories are **frozen**. They are a reference corpus, historical
record, and evidence source. They are never modified from here, their Git history is never
imported here, and nothing enters this repository merely because it exists there.

When authority is unclear: **do not guess — record the ambiguity and stop the transfer.**
