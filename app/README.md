# app — runnable applications

**Status: M0 IMPLEMENTATION ADMITTED (ADR-0006).**

## Purpose

Applications that are run, as distinct from `core/` (canonical semantics, which
applications call) and `cli/` (the operator surface across the whole product, still
reserved).

## What is here

- [`verifier/`](verifier/) — the M0 Evidence Package verifier. Run it with:

  ```sh
  python3 -m app.verifier <package-directory> --json
  ```

  Exit status is the machine-readable result: `0` VERIFIED, `2` TAMPERED, `3` INVALID.

## Gate

The verifier may depend on the package it is given and on `core/`. It must not depend on
the producer runtime, the original database, a network, hidden state, policy-engine
execution, or a developer environment (ADR-0006 §2). `tools/independence_check.py`
enforces this by running it in a directory containing only `core/` and `app/`.

Anything placed here that derives from the frozen `Aura-IDToken` corpus requires a
transfer register entry at `TRANSFER_APPROVED` or later. Nothing here does: M0 is new
implementation, written against ADR-0005 and ADR-0006.
