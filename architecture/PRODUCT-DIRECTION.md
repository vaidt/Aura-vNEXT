# Aura vNEXT — Product Direction

- **Document status:** NON-NORMATIVE
- **Established:** 2026-08-27

> **This document does not authorise implementation of anything it describes.**
> It records intended direction so that decisions taken now are not accidentally
> incompatible with it. Each capability below requires its own architecture decision
> before any implementation begins.

## 1. Positioning

Aura vNEXT is intended to become **Evidence-First Runtime Governance for AI Agents**.

The distinguishing claim is not that an action was *allowed*. It is that the resulting
execution can be **reconstructed, verified, and supported by evidence**.

A policy gateway answers: *was this permitted?*
Aura aims to answer: *what actually happened, can it be replayed, and can the answer be
proven to a third party who does not trust the runtime?*

## 2. The governed chain

```
CONTEXT ─▶ DECISION ─▶ ACTION ─▶ OUTPUT ─▶ AUDIT ─▶ EVIDENCE ─▶ VERIFICATION
```

| Stage | Question it must answer |
| --- | --- |
| CONTEXT | What did the agent know, and where did it come from? |
| DECISION | What was decided, under which policy, at which version? |
| ACTION | What was attempted, with what parameters, against what system? |
| OUTPUT | What was produced, and what was allowed to leave? |
| AUDIT | What is the tamper-evident record of the above? |
| EVIDENCE | What artifact can be handed to a third party? |
| VERIFICATION | Can that artifact be checked independently of Aura? |

Verification closing the loop back to context is the point of the architecture. A stage
that cannot be verified is a gap in the claim, not a detail.

## 3. Candidate capabilities

Direction only. Nothing below is scheduled, designed, or authorised.

- deterministic policy enforcement
- context governance
- action governance
- output governance
- append-only audit
- cryptographic evidence
- deterministic replay
- compliance evidence packages
- agent integrations
- policy / governance packs
- CLI verification
- reporting
- developer and agent integrations

## 4. Differentiation

Aura should differentiate on:

- **determinism** where applicable — identical inputs yield identical decisions;
- **evidence integrity** — the record resists tampering and says so verifiably;
- **provenance** — every input to a decision is attributable;
- **replayability** — an execution can be reconstructed from the record alone;
- **cryptographic audit** — integrity claims rest on primitives, not on trust in the runtime;
- **explicit verification** — a third party can check the claim without Aura's cooperation;
- **compliance-oriented evidence artifacts** — output usable as evidence, not just as logs.

## 5. Competitive reference

AutoPIL and comparable products may be used as **competitive reference points** —
to understand the market and to sharpen requirements.

Their implementation, architecture, terminology, and proprietary material must not be
copied. This is enforced as acceptance criterion **C11** in
`governance/MODULE-ACCEPTANCE-CRITERIA.md` and applies to work written here, not only to
transferred artifacts.

The objective is a stronger evidence and verification layer — not another policy gateway.

## 6. Scope discipline

Product direction is not a backlog and does not expand scope. Implementing any capability
in §3 requires an ADR that states the requirement, the boundary affected, the tests
required, and the consequences accepted.
