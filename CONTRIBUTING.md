# Contributing to Aura vNEXT

The contribution rules are normative and live in
[`governance/DEVELOPMENT-RULES.md`](governance/DEVELOPMENT-RULES.md).

Read these first:

1. [`governance/GENESIS.md`](governance/GENESIS.md) — what is fixed and what is deliberately open
2. [`governance/REPOSITORY-BOUNDARY.md`](governance/REPOSITORY-BOUNDARY.md) — the boundary against the frozen corpus
3. [`governance/DEVELOPMENT-RULES.md`](governance/DEVELOPMENT-RULES.md) — how to work here

Before pushing:

```sh
make check
```

Two rules worth repeating here, because they are the ones most often broken under pressure:

- **Nothing enters this repository from the frozen corpus without a transfer register entry
  at `TRANSFER_APPROVED` or later.**
- **A test is never weakened, skipped, or narrowed to make CI pass.**
