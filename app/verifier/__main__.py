"""Command-line entry point: ``python3 -m app.verifier <package-directory>``.

Exit status is the machine-readable result:
    0  VERIFIED
    2  TAMPERED
    3  INVALID
    64 usage error
"""

from __future__ import annotations

import argparse
import json
import sys

from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package

EXIT_STATUS = {VERIFIED: 0, TAMPERED: 2, INVALID: 3}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aura-verify", description=__doc__)
    parser.add_argument("package", help="path to the evidence package directory")
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = parser.parse_args(argv)

    result = verify_package(args.package)

    if args.json:
        print(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    else:
        print(result.status)
        for reason in result.reasons:
            print(f"  - {reason}", file=sys.stderr)

    return EXIT_STATUS[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
