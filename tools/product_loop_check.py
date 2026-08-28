#!/usr/bin/env python3
"""Run the M0 product loop end to end and report what it produced.

This is the acceptance experiment, executed rather than described:

    APPLICATION EVENT -> aura record -> Evidence Package -> aura verify -> VERIFIED
                         mutate the decision   -> TAMPERED
                         malform the package   -> INVALID
                         copy to a clean room  -> VERIFIED

Environment A produces the package by running the `aura` command line as a separate
process, exactly as an application would. Environment B is built by
`independence_check.build_environment`: a directory outside this repository holding
`core/` and the verifier half of `app/` and nothing else, run in isolated mode with
the environment cleared and the network disabled. Only the package crosses between
them.

Standard library only (ADR-0002/ADR-0004).

Usage:
    python3 tools/product_loop_check.py [--keep DIR]

Prints a plain-text execution record and exits non-zero if any expected result was
not obtained. The record states the conditions actually exercised: one platform, one
Python build. No cross-platform claim is made.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "tools"))

import independence_check  # noqa: E402

PACKAGE_ID = "aura-evidence-loan-001"

POLICY = {
    "policy_id": "loan.underwriting",
    "version": 2,
    "rules": [
        {"id": "LOAN.DTI_EXCEEDED", "action": "BLOCK", "threshold_bp": 4300},
        {"id": "LOAN.MANUAL_REVIEW", "action": "FLAG", "threshold_bp": 5000},
    ],
}

# The application events, in the order the application reached them.
EVENTS = [
    ["--decision", "ALLOW", "--request-id", "loan-001-intake",
     "--input-hash", "b" * 64, "--timestamp", "2026-08-27T09:15:00Z",
     "--metadata", "actor=agent-17", "--metadata", "stage=intake"],
    ["--decision", "REQUIRE_APPROVAL", "--request-id", "loan-001-assess",
     "--input-hash", "c" * 64, "--timestamp", "2026-08-27T09:15:04Z",
     "--shadow-hash", "a" * 64,
     "--violation", "LOAN.DTI_EXCEEDED:BLOCK:0.95",
     "--violation", "LOAN.MANUAL_REVIEW:FLAG:0.5",
     "--metadata", "actor=agent-17", "--metadata", "stage=assess",
     "--metadata", 'note=ratio 0.47 | flagged "high" \\ review'],
    ["--decision", "DENY", "--request-id", "loan-001-settle",
     "--input-hash", "a" * 64, "--timestamp", "2026-08-27T09:16:31Z",
     "--violation", "LOAN.DTI_EXCEEDED:BLOCK:1.0",
     "--metadata", "actor=reviewer-3", "--metadata", "stage=settle",
     # An empty value is a present member, not an absent one.
     "--metadata", "note="],
]

# The accepted M0 reference package. The command line above states the same scenario
# an operator would type; the bytes it produces are compared against this.
REFERENCE_PACKAGE = REPO_ROOT / "evidence/examples/aura-evidence-loan-001"

# expected/result.json is non-normative fixture metadata (contract section 6.2) and
# is added by the fixture generator, not by the producer, so it is not compared.
PRODUCED_FILES = ("manifest.json", "evidence/audit.jsonl", "evidence/policy.json",
                  "evidence/genesis.json")


def _aura(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "app.aura", *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120,
    )


def produce(environment_a: Path) -> Path:
    """Environment A: turn the application events into an Evidence Package."""
    policy_path = environment_a / "policy.json"
    policy_path.write_text(json.dumps(POLICY, indent=2) + "\n", encoding="utf-8")
    package = environment_a / PACKAGE_ID

    for index, event in enumerate(EVENTS):
        command = ["record", "--output", str(package), "--policy", str(policy_path)]
        if index:
            command.append("--append")
        completed = _aura(*command, *event)
        if completed.returncode != 0:
            raise RuntimeError(
                f"aura record failed on event {index} "
                f"({completed.returncode}): {completed.stderr}"
            )
    return package


def _mutate_decision(package: Path) -> None:
    """Flip the recorded outcome and repair the manifest digests.

    Repairing the outer checksum is the point: without it the mutation would be
    caught by a file digest and the canonical binding would never be tested.
    """
    audit = package / "evidence/audit.jsonl"
    lines = audit.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    record["decision"] = "ALLOW"
    lines[-1] = json.dumps(record, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
    audit.write_text("\n".join(lines) + "\n", encoding="utf-8")
    independence_check._repair_manifest(package)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep", type=Path, default=None,
                        help="write the produced package here as well")
    args = parser.parse_args(argv)

    print("M0 PRODUCT LOOP -- EXECUTION RECORD")
    print(f"  python    : {platform.python_implementation()} {platform.python_version()}")
    print(f"  platform  : {platform.system()} {platform.machine()}")
    print("  producer  : environment A, `aura record` as a separate process")
    print("  verifier  : environment B, core/ + app/verifier only, isolated, no network")
    print("  crossing  : the evidence package directory, and nothing else")
    print("  note      : single-platform run. No cross-platform claim is made.")
    print()

    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="aura-env-a-") as a, \
            tempfile.TemporaryDirectory(prefix="aura-env-b-") as b:
        environment_a = Path(a)
        environment_b = Path(b)

        # 1. EVENT -> PRODUCER -> PACKAGE
        package = produce(environment_a)
        entries = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        print(f"  {len(EVENTS)} application event(s) -> {PACKAGE_ID}")
        print(f"  chain head              : {entries['chain_head']}")
        print(f"  entries                 : {entries['entry_count']}")
        print()

        # 2. The bytes the operator surface produced are the accepted reference
        #    package. This is what makes the loop a product path rather than a
        #    parallel one: `aura record`, driven by hand-typed flags, reproduces the
        #    package M0 accepted, byte for byte.
        divergent = [
            name for name in PRODUCED_FILES
            if (package / name).read_bytes() != (REFERENCE_PACKAGE / name).read_bytes()
        ]
        if divergent:
            failures.append(
                f"the produced package differs from the accepted reference package: "
                f"{', '.join(divergent)}"
            )
        print(f"  reproduces reference    -> "
              f"{'yes' if not divergent else 'NO (' + ', '.join(divergent) + ')'}")

        # 3. PACKAGE -> VERIFIER (the product surface)
        verified = _aura("verify", str(package))
        print(f"  aura verify             -> {verified.stdout.strip().splitlines()[-1]}")
        if verified.returncode != 0:
            failures.append(f"aura verify returned {verified.returncode}")

        # 4. The same package, verified where the producer is not.
        env = independence_check.build_environment(environment_b)
        delivered = environment_b / "delivered"
        shutil.copytree(package, delivered)
        result = independence_check.run(env, delivered)
        print(f"  clean-room package      -> {result['status']}")
        if result["status"] != "VERIFIED":
            failures.append(f"clean-room package returned {result['status']}")
        if result["_environment"]["repo_importable"]:
            failures.append("the repository was importable inside the clean room")
        leaked = [m for m in result["_environment"]["modules"]
                  if m.startswith(("tools", "tests", "app.producer", "app.aura"))]
        if leaked:
            failures.append(f"producer-side modules were importable: {leaked}")
        if (env / "app" / "producer").exists() or (env / "app" / "aura").exists():
            failures.append("the producer was present in the clean-room environment")

        # 5. Mutate the recorded decision.
        mutated = environment_b / "mutated"
        shutil.copytree(package, mutated)
        _mutate_decision(mutated)
        result = independence_check.run(env, mutated)
        print(f"  decision DENY -> ALLOW  -> {result['status']}")
        if result["status"] != "TAMPERED":
            failures.append(f"mutated package returned {result['status']}")

        # 6. Malform the package.
        malformed = environment_b / "malformed"
        shutil.copytree(package, malformed)
        (malformed / "manifest.json").write_text("{ not json", encoding="utf-8")
        result = independence_check.run(env, malformed)
        print(f"  malformed package       -> {result['status']}")
        if result["status"] != "INVALID":
            failures.append(f"malformed package returned {result['status']}")

        if args.keep:
            shutil.copytree(package, args.keep, dirs_exist_ok=True)
            print(f"\n  produced package kept at {args.keep}")

    print()
    if failures:
        print("RESULT: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULT: PASS -- event -> package -> VERIFIED, "
          "and TAMPERED / INVALID both reproduced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
