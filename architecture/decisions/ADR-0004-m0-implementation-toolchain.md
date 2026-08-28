# ADR-0004 — M0 is implemented in Python 3.11 using the standard library only

- **Status:** ACCEPTED
- **Date:** 2026-08-27
- **Closes:** OQ-2 (for M0 scope), OQ-4 (for M0 scope)

## Context

OQ-2 records that no primary implementation language has been chosen, and ADR-0003 is
explicit that the Genesis tooling being Python "is not a language decision and does not
bind `core/`".

M0 cannot be implemented without closing that question, because M0's deliverable is a
byte-exact canonical form. The language's string, map, and number semantics are not an
implementation detail of such a thing: they determine what the bytes are.

Two properties dominate the choice for M0:

- **A verifier a third party can actually run.** The product claim is independent
  verification. A verifier requiring a toolchain, a package manager, and a lockfile is
  weaker evidence than one requiring an interpreter that is already present.
- **No dependency policy exists yet (OQ-4).** Any third-party dependency would decide
  OQ-4 by convenience, which `governance/OPEN-QUESTIONS.md` forbids.

## Decision

M0 — `core/`, `app/verifier/`, its tests, and its tooling — is implemented in **Python
3.11 using the standard library only**. No third-party runtime or test dependencies.

This binds **M0 only**. It does not decide the language of `runtime/`, `policy/`,
`audit/`, `integrations/`, or `packs/`, and it is not a claim that Python is the right
language for a production enforcement runtime. Those remain open.

Three standard-library facilities are load-bearing and are named here because M0's
correctness rests on them: `hashlib.sha256`, `decimal.Decimal` (for the confidence
scale, ADR-0005 §5), and `str.encode("utf-16-be")` (for RFC 8785 member ordering).

## Alternatives considered

- **Rust or Go.** Better fits for a production runtime, and both give a single-binary
  verifier. Rejected for M0 because they would decide OQ-2 for the whole product on the
  strength of one milestone, and because a compiled verifier is harder for a reviewer to
  read against the canonical-byte vectors than the vectors themselves.
- **A JSON canonicalisation library.** Rejected: it decides OQ-4, and it would place the
  definition of the canonical form outside this repository, where it could change under
  a version bump. The canonical form is the product; it is not delegated.
- **Deferring M0 until OQ-2 is decided product-wide.** Rejected: that decision needs
  evidence about the runtime, which M0 does not produce. Blocking M0 on it would trade a
  bounded decision for an unbounded wait.

## Consequences

- The verifier runs anywhere CPython 3.11 runs, with no installation step.
- Python's own floating-point and iteration-order behaviour must be actively excluded
  from the canonical form rather than trusted. ADR-0005 does this by forbidding floats
  and by sorting members explicitly; `tests/conformance/` holds the checks.
- A future production runtime in another language must reproduce the canonical bytes in
  `conformance/vectors/`. Those vectors, not this implementation, are the contract.
- OQ-2 and OQ-4 remain open beyond M0 and must be closed before any module outside M0
  is implemented.
