"""Shared helpers for the product-loop suites.

These build packages the way the product does -- through ``app.producer`` and the
``aura`` command line -- rather than by copying a committed fixture. A suite that
only ever mutated the checked-in package would test the fixture; the point here is
to test what an application actually produces.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _m0 import REPO_ROOT  # noqa: F401  (re-exported for the product suites)

# The loan scenario is defined once, with the fixture generator. Restating it here
# would create a second "loan-001" that could drift from the committed reference
# package while every suite stayed green. Importing it means the product suites
# produce exactly the package `evidence/examples/` holds.
from build_m0_fixtures import LOAN_EVENTS, LOAN_POLICY, PACKAGE_ID  # noqa: E402

from app.producer import build_package, write_package

__all__ = [
    "REPO_ROOT", "LOAN_POLICY", "LOAN_EVENTS", "PACKAGE_ID",
    "produce_loan_package", "run_aura", "write_policy",
]


def produce_loan_package(destination: Path, *, package_id: str = PACKAGE_ID) -> Path:
    """Produce the loan package into ``destination`` and return its directory."""
    target = Path(destination) / package_id
    write_package(target, build_package(package_id, LOAN_POLICY, LOAN_EVENTS))
    return target


def write_policy(directory: Path, policy: dict | None = None) -> Path:
    """Write a policy document an application would pass to ``aura record``."""
    import json

    path = Path(directory) / "policy.json"
    path.write_text(
        json.dumps(LOAN_POLICY if policy is None else policy, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def run_aura(*args: str) -> subprocess.CompletedProcess:
    """Run the `aura` command line as a separate process, from the repository root."""
    return subprocess.run(
        [sys.executable, "-m", "app.aura", *args],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
