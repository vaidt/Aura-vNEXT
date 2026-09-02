# Operating Aura M0

**Audience:** an engineer who has this repository and nothing else. No prior knowledge of
Aura's internals is assumed, and none is needed. Everything below runs from a clean
checkout, offline, with no database, no service, and no configuration.

This document describes how to operate the product. It is not normative: the contract it
serves is [`contract/M0-EVIDENCE-CONTRACT.md`](contract/M0-EVIDENCE-CONTRACT.md), and
where the two ever disagree, the contract is right.

---

## 1. What Aura M0 does

Aura M0 **produces and verifies portable evidence of an AI-system decision.**

When an application decides something — allow, deny, escalate — Aura records that decision
as a sealed entry in an append-only chain, and packages the chain into a directory called
an **Evidence Package**. That directory can be copied to anyone. They can establish, from
the directory alone, whether the evidence is intact and unaltered since it was sealed.

```
AI / APPLICATION
       |
       v
  AUDIT EVENT
       |
       v
EVIDENCE PACKAGE  ---- copy ---->  INDEPENDENT VERIFIER
                                          |
                                   VERIFIED / TAMPERED / INVALID
```

The verifier needs the package and nothing else. It does not call the producer, read a
database, or reach the network.

---

## 2. Requirements

- Python 3.11.
- Nothing else. There are no dependencies to install, and no network access is used.

Run every command from the repository root.

---

## 3. The workflow

```
CREATE  ->  INSPECT  ->  COPY  ->  VERIFY
 record     package               verify
```

Copy and paste this. It works from a clean checkout exactly as written.

<!-- operator-walkthrough: this block is executed verbatim by tests/product/test_documented_workflow.py -->

```sh
# 1. CREATE -- record a decision your application reached.
python3 -m app.aura record \
    --output ./my-first-package \
    --policy evidence/examples/aura-evidence-loan-001/evidence/policy.json \
    --decision DENY \
    --request-id loan-001 \
    --input-file README.md \
    --violation LOAN.DTI_EXCEEDED:BLOCK:0.95

# 2. INSPECT -- see what the package holds and what each file in it is for.
python3 -m app.aura package ./my-first-package

# 3. COPY -- a package is an ordinary directory. Move it however you move files.
cp -r ./my-first-package ./delivered-package

# 4. VERIFY -- from the copy alone.
python3 -m app.aura verify ./delivered-package
```

Step 4 prints `Result: VERIFIED` and exits `0`.

`--input-file` is used above because it needs no preparation: Aura digests the file's bytes
and records the digest. **The input itself is never stored in the package** — only a
reference to it. If your application already has the digest, pass `--input-hash` instead.

To record a second decision into the same package, run `record` again with `--append`:

```sh
python3 -m app.aura record --append \
    --output ./my-first-package \
    --policy evidence/examples/aura-evidence-loan-001/evidence/policy.json \
    --decision ALLOW --request-id loan-002 --input-file CONTRIBUTING.md
```

Each append extends the chain. Recording into an existing package **without** `--append` is
refused, so evidence already recorded cannot be overwritten by accident.

---

## 4. What is in an Evidence Package

`aura package` will tell you this for any package you are handed. For reference:

| File | What it is |
| --- | --- |
| `evidence/audit.jsonl` | **The evidence.** One sealed decision record per line, each linked to the one before it. |
| `evidence/policy.json` | **The policy.** The document the decisions were taken under. Every record is bound to it. |
| `evidence/genesis.json` | **The anchor.** Where the record chain starts — the trust anchor for record 0. |
| `manifest.json` | **The commitment.** What the package claims to be, where its record chain ends, and a digest for every file above. |

Anything else in the directory is not evidence. The verifier does not read it, and
`aura package` marks it as such. In the reference package, `expected/result.json` and
`README.md` are both in that category — a package's own claim about its verdict has no
bearing on the verdict it receives.

A package is **self-contained**: those four files are everything verification needs.

---

## 5. The three results

`aura verify` returns exactly one of three results. They are never collapsed into each
other, and only the first is acceptance.

| Result | Meaning |
| --- | --- |
| **VERIFIED** | The package satisfies the M0 integrity and verification contract. |
| **TAMPERED** | The package is recognisable as M0 evidence, but protected evidence fails integrity verification. |
| **INVALID** | The package cannot be interpreted as a valid M0 Evidence Package. |

The difference between the last two is worth holding on to:

- **TAMPERED** means *this is M0 evidence, and it has been altered.* Something protected —
  a decision, the policy, the chain, the manifest's commitment — no longer matches what was
  sealed.
- **INVALID** means *this is not something I can read as M0 evidence at all.* A missing
  manifest, unreadable JSON, a profile this build does not implement, a record that is not
  an audit entry.

A package that cannot be parsed is `INVALID` even where a digest would also have failed.
Both are refusals. **Only `VERIFIED` is acceptance.**

### Exit statuses

Every command reports its outcome in its exit status, so a script that never reads the
output still gets the answer.

| Status | Meaning |
| --- | --- |
| `0` | `verify`: **VERIFIED**. Other commands: succeeded. |
| `2` | `verify`: **TAMPERED**. |
| `3` | `verify`: **INVALID**. |
| `64` | The command line could not be understood — a missing argument, an unknown flag. |
| `65` | The command was understood, and could not be carried out — an unreadable policy file, a package that already exists. |
| `141` | Output was cut short because a pipe closed (`... | head`). No verdict was delivered. |

`64` and `65` are deliberately outside the verdict range. A mistyped flag can never be
mistaken for a failed integrity check.

`aura package` never returns `2` or `3`. Describing a package is not verifying one.

---

## 6. Seeing TAMPERED and INVALID for yourself

Do not take the three results on trust. Reproduce them:

```sh
python3 tools/product_loop_check.py
```

That runs the whole loop and prints what it obtained at each step: an application event is
recorded through `aura record`, the package is verified `VERIFIED`, a recorded decision is
altered and comes back `TAMPERED`, the manifest is broken and comes back `INVALID`, and the
package is verified once more in a directory that does not contain the producer at all.

To do it by hand on a package you produced above:

```sh
# TAMPERED -- alter a protected value.
cp -r ./my-first-package ./altered
sed -i 's/"decision":"DENY"/"decision":"ALLOW"/' ./altered/evidence/audit.jsonl
python3 -m app.aura verify ./altered            # -> TAMPERED, exit 2

# INVALID -- break the package structure.
cp -r ./my-first-package ./broken
echo '{ not json' > ./broken/manifest.json
python3 -m app.aura verify ./broken             # -> INVALID, exit 3
```

---

## 7. When something goes wrong

`verify` prints the verdict on stdout and the reasons on stderr. The reasons name the file
and what did not match.

| What you did | What you get |
| --- | --- |
| Pointed at a path that does not exist | `INVALID` — *not a directory* |
| Pointed at a file instead of a package directory | `INVALID` — *not a directory* |
| The package has no `manifest.json` | `INVALID` — *required file is missing* |
| `manifest.json` is not valid JSON | `INVALID` — *malformed JSON* |
| The package declares a profile this build does not implement | `INVALID` — *unsupported profile* |
| A file the manifest declares is not there | `INVALID` — *declared in the manifest but not present* |
| An audit record is not a well-formed audit entry | `INVALID` |
| A recorded decision was edited | `TAMPERED` — the record's digest no longer matches its content |
| The policy document was edited | `TAMPERED` — the records no longer name the policy the package carries |
| A record was removed from the end of the chain | `TAMPERED` — the chain no longer ends where the manifest says |
| The manifest declares a digest that does not match the file | `TAMPERED` |

For `record`:

| What you did | What you get |
| --- | --- |
| Gave a `--policy` file that does not exist, or is not JSON | Exit `65`, message on stderr |
| Gave neither `--input-hash` nor `--input-file` | Exit `65` |
| Gave an `--input-hash` that is not 64 lowercase hex characters | Exit `65` |
| Recorded into a directory that already holds a package | Exit `65` — pass `--append`, or choose another `--output` |
| Used `--append` on a directory that holds no package | Exit `65` |
| Mistyped a flag, or gave a `--decision` outside the three allowed | Exit `64` |

Every one of these is refused before anything is written. `record` does not leave a
half-built package behind.

---

## 8. What Aura does not claim

This is as important as what it does claim. A `VERIFIED` result establishes **integrity**,
and integrity alone.

- **Integrity ≠ correctness.** That a decision was sealed unaltered says nothing about
  whether it was the right decision.
- **Integrity ≠ fairness.** Aura does not evaluate the policy or its outcomes.
- **Integrity ≠ legality.** Aura makes no regulatory or legal claim of any kind, and a
  `VERIFIED` package is not evidence of compliance with anything.
- **Integrity ≠ authenticity.** M0 defines no signature scheme. `VERIFIED` does not
  establish who produced the package.
- **Integrity ≠ authorship.** Anyone able to rewrite every record and the manifest can
  produce a self-consistent package. `VERIFIED` means *this package is internally
  consistent and has not been altered since it was sealed* — not *this package is genuine.*

What M0 detects is **alteration of an existing package**, which is the threat it was built
for. See the contract §7 and `core/signing/README.md`.

M0 is a **single-platform** result: everything above has been executed on one platform and
one Python build. No cross-platform or cross-language claim is made.

---

## 9. Command reference

### `aura record`

Turn an application event into an Evidence Package.

```
python3 -m app.aura record --output DIR --policy FILE [options]
```

| Argument | | Purpose |
| --- | --- | --- |
| `--output DIR` | required | Package directory to create, or to extend with `--append`. |
| `--policy FILE` | required | The policy document the decision was taken under. JSON. |
| `--decision {ALLOW,DENY,REQUIRE_APPROVAL}` | required¹ | The decision the application reached. |
| `--request-id ID` | required¹ | The application's identifier for this decision. |
| `--input-hash HEX64` | one of² | Digest of the decision input, already computed. |
| `--input-file FILE` | one of² | Local file whose bytes are digested to the input reference. |
| `--timestamp RFC3339` | optional | `YYYY-MM-DDThh:mm:ssZ`. Defaults to now, UTC. |
| `--violation R:A:C` | optional | `RULE:ACTION:CONFIDENCE`. Repeatable; order is preserved. |
| `--metadata KEY=VALUE` | optional | String metadata. Repeatable. |
| `--policy-repr TEXT` | optional | Human-readable policy label. Derived from the policy document by default. |
| `--shadow-hash HEX64` | optional | Optional shadow digest. Absent when not given. |
| `--package-id ID` | optional | Package identifier. Defaults to the output directory's name. |
| `--events FILE` | optional | A JSON array of events, recorded as one chain, instead of the flags above. |
| `--append` | optional | Extend the chain of an existing package. One event per run. |
| `--json` | optional | Emit the result as JSON on stdout. |

¹ Required unless `--events` is used. ² Exactly one of `--input-hash` / `--input-file`.

**Output:** a summary on stdout — profile, package id, entry count, chain head. Errors on
stderr. **Exit:** `0` recorded, `64` command line, `65` refused.

### `aura package`

Describe what a package contains. Read-only; it changes nothing.

```
python3 -m app.aura package DIR [--json]
```

**Output:** on stdout, the package's identity and chain terminus, every file and what it is
for, which files the manifest declares, and the decisions recorded. A declared file that is
absent is marked `(MISSING)`; a file the manifest does not declare is marked as not
evidence. Errors on stderr. **Exit:** `0` described, `64` command line, `65` could not be
read, or the manifest declares a path outside the package (section 6.1 of the evidence
contract — the same boundary `verify` enforces, refused here rather than described).
**Never `2` or `3`** — this command does not return a verdict.

### `aura verify`

Verify a package from its directory alone.

```
python3 -m app.aura verify DIR [--json]
```

**Output:** the verdict on stdout (`Result: VERIFIED` / `TAMPERED` / `INVALID`); the reasons
for a refusal on stderr, one per line, each naming the file and what did not match. With
`--json`, a single JSON object on stdout carrying `status`, `package_id`, `entries`, and
`reasons`. **Exit:** `0` VERIFIED, `2` TAMPERED, `3` INVALID, `64` command line.

---

## 10. Where to go next

| Document | Purpose |
| --- | --- |
| [`contract/M0-EVIDENCE-CONTRACT.md`](contract/M0-EVIDENCE-CONTRACT.md) | The normative contract: canonical form, digest, package, verifier |
| [`../evidence/examples/aura-evidence-loan-001/README.md`](../evidence/examples/aura-evidence-loan-001/README.md) | The reference package, and how it was produced |
| [`../architecture/decisions/ADR-0006-m0-evidence-package-and-verifier.md`](../architecture/decisions/ADR-0006-m0-evidence-package-and-verifier.md) | Why the package and verifier are shaped this way |
