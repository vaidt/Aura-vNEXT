# Aura vNEXT

**Status: M0 — canonical evidence domain implemented and gated.**

Aura vNEXT is a **new product** and the **new canonical implementation** of Aura. It is
not a fork, mirror, migration, or Git merge of the frozen `Aura-IDToken` repositories.

## What this repository is right now

**M0 is implemented**: the canonical evidence domain, the audit chain binding, the
portable Evidence Package, and an independent three-state verifier. See
[`docs/contract/M0-EVIDENCE-CONTRACT.md`](docs/contract/M0-EVIDENCE-CONTRACT.md).

> **M0's canonical form is defined here, not recovered.** The frozen `Aura-IDToken`
> corpus is not reachable from this environment, so **no compatibility claim** is made
> with any prior Aura implementation. See the contract §0 and OQ-8.

### Try it

```sh
python3 -m app.verifier evidence/examples/aura-evidence-loan-001 --json   # -> VERIFIED
python3 tools/independence_check.py    # VERIFIED / TAMPERED / INVALID, in isolation
make check                             # every gate
```

### Genesis (still in force)

Genesis established the foundation required before any implementation is admitted:

- the repository boundary between the frozen source corpus and this canonical target,
- the provenance policy that governs how any legacy artifact may enter,
- the transfer register that records every candidate artifact and its status,
- the module acceptance criteria that gate transfer,
- the architecture decision records for the above,
- a minimal CI baseline that enforces these invariants.

No implementation modules have been transferred from the corpus, and none are approved
for transfer. The register still holds **zero** entries. M0 is new implementation written
against ADR-0005 and ADR-0006, not transferred material — the transfer gate is untouched
by it.

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
| [`docs/contract/M0-EVIDENCE-CONTRACT.md`](docs/contract/M0-EVIDENCE-CONTRACT.md) | The normative M0 contract: canonical form, digest, package, verifier |
| [`architecture/decisions/`](architecture/decisions/) | Architecture decision records |

## Repository layout

`core/`, `app/`, `conformance/vectors/`, and `evidence/examples/` are **populated by M0**
(ADR-0006 §4). Every other domain directory remains **reserved** — `tests/test_structure.py`
asserts they hold no implementation, so M0 cannot sprawl. Each directory carries a
`README.md` stating its purpose and the gate governing what may be placed in it.

```
app/             runnable applications — the M0 verifier
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

## Gates

Dependency-free throughout — Python 3.11 standard library only (ADR-0002, ADR-0004):

| Gate | Command | What it establishes |
| --- | --- | --- |
| Structure | `make structure` | Layout, ADR index, boundary, M0 scope fence |
| Register | `make register` | The transfer register is valid |
| Fixtures | `make fixtures` | Committed canonical bytes match the implementation (P0-02, P0-03) |
| Tests | `make test` | Governance invariants, conformance, mutation gate |
| Independence | `make independence` | The verifier works from the package alone |

`make check` runs all of them.

## Boundary reminder

The `Aura-IDToken` repositories are **frozen**. They are a reference corpus, historical
record, and evidence source. They are never modified from here, their Git history is never
imported here, and nothing enters this repository merely because it exists there.

When authority is unclear: **do not guess — record the ambiguity and stop the transfer.**
