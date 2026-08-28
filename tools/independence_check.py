#!/usr/bin/env python3
"""Run the M0 verifier in an isolated environment and report what it produced.

Builds a fresh directory containing **only** `core/` and `app/` plus a copy of the
package under test, then runs the verifier there as a separate process with:

  * ``-I``  -- isolated mode: PYTHONPATH and the user site directory are ignored,
               and the repository is not importable;
  * a cleared environment;
  * a working directory outside the repository;
  * ``socket`` disabled before the verifier is imported, so any network access
    raises instead of succeeding quietly.

The producer is not present in that directory. Neither are `tools/`, `tests/`, the
fixture generator, or the repository itself.

Usage:
    python3 tools/independence_check.py [--package PATH]

Prints a plain-text execution record and exits non-zero if any expected result
was not obtained.
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
DEFAULT_PACKAGE = REPO_ROOT / "evidence/examples/aura-evidence-loan-001"

RUNNER = '''
import json, os, sys

# -I (isolated mode) strips the script directory from sys.path, so the one importable
# location is added back explicitly. It holds only core/ and app/: no producer, no
# fixture generator, no test support, and not the repository.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Disable the network before the verifier is imported. If verification needed a
# network call, it would now raise rather than silently succeed.
import socket
class NetworkAccessAttempted(RuntimeError):
    pass
def _deny(*args, **kwargs):
    raise NetworkAccessAttempted("the verifier attempted network access")
socket.socket = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny
socket.gethostbyname = _deny

from app.verifier import verify_package

result = verify_package(sys.argv[1]).as_dict()
result["_environment"] = {
    "sys_path": list(sys.path),
    "repo_importable": any("Aura-vNEXT" in p for p in sys.path),
    "modules": sorted(m for m in sys.modules
                      if m.split(".")[0] in ("core", "app", "tools", "tests")),
}
print(json.dumps(result))
'''


def build_environment(root: Path) -> Path:
    """Create a verifier environment holding only what verification may use."""
    env = root / "verifier-env"
    env.mkdir()
    for package in ("core", "app"):
        shutil.copytree(REPO_ROOT / package, env / package)
    (env / "runner.py").write_text(RUNNER, encoding="utf-8")
    return env


def run(env: Path, package: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, "-I", "runner.py", str(package)],
        cwd=env, env={"PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=120,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"verifier process failed ({completed.returncode}): {completed.stderr}"
        )
    return json.loads(completed.stdout)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=DEFAULT_PACKAGE)
    args = parser.parse_args(argv)

    print("M0 INDEPENDENT VERIFICATION -- EXECUTION RECORD")
    print(f"  python   : {platform.python_implementation()} {platform.python_version()}")
    print(f"  platform : {platform.system()} {platform.machine()}")
    print(f"  package  : {args.package.relative_to(REPO_ROOT)}")
    print("  note     : single-platform run. No cross-platform claim is made.")
    print()

    failures = []
    with tempfile.TemporaryDirectory(prefix="aura-m0-independence-") as tmp:
        root = Path(tmp)
        env = build_environment(root)

        # 1. Pristine package.
        pristine = root / "pristine"
        shutil.copytree(args.package, pristine)
        result = run(env, pristine)
        print(f"  pristine package        -> {result['status']}")
        if result["status"] != "VERIFIED":
            failures.append(f"pristine package returned {result['status']}")
        if result["_environment"]["repo_importable"]:
            failures.append("the repository was importable inside the isolated run")
        leaked = [m for m in result["_environment"]["modules"]
                  if m.startswith(("tools", "tests"))]
        if leaked:
            failures.append(f"producer-side modules were importable: {leaked}")

        # 2. Mutated package: a protected field altered, manifest repaired.
        mutated = root / "mutated"
        shutil.copytree(args.package, mutated)
        audit = mutated / "evidence/audit.jsonl"
        lines = audit.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[0])
        record["decision"] = "DENY"
        lines[0] = json.dumps(record, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"))
        audit.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _repair_manifest(mutated)
        result = run(env, mutated)
        print(f"  mutated package         -> {result['status']}")
        if result["status"] != "TAMPERED":
            failures.append(f"mutated package returned {result['status']}")

        # 3. Malformed package.
        malformed = root / "malformed"
        shutil.copytree(args.package, malformed)
        (malformed / "manifest.json").write_text("{ not json", encoding="utf-8")
        result = run(env, malformed)
        print(f"  malformed package       -> {result['status']}")
        if result["status"] != "INVALID":
            failures.append(f"malformed package returned {result['status']}")

    print()
    if failures:
        print("RESULT: FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("RESULT: PASS -- VERIFIED / TAMPERED / INVALID all reproduced in isolation")
    return 0


def _repair_manifest(package: Path) -> None:
    import hashlib

    path = package / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["files"] = {
        name: hashlib.sha256((package / name).read_bytes()).hexdigest()
        for name in manifest["files"]
    }
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
