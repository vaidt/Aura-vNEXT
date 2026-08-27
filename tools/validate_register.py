#!/usr/bin/env python3
"""Validate the Aura vNEXT module transfer register.

Enforces the schema in ``provenance/transfer-register.schema.json`` plus the conditional
rules documented in ``provenance/TRANSFER-REGISTER.md`` section 4 -- the rules JSON Schema
cannot express, and the ones that actually matter: an artifact must never reach approval
merely because it builds.

Standard library only (ADR-0002).

Usage:
    python3 tools/validate_register.py [--repo-root PATH]
Exit status 0 when the register is valid, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jsonschema_mini  # noqa: E402

REGISTER = Path("provenance/transfer-register.json")
SCHEMA = Path("provenance/transfer-register.schema.json")
RECORDS_DIR = Path("provenance/records")

SHA1 = re.compile(r"^[0-9a-f]{40}$")

# Statuses that permit corpus-derived material to exist in this repository.
ADMITTING = {"TRANSFER_APPROVED", "TRANSFERRED"}

# Criteria applicable per artifact class -- MODULE-ACCEPTANCE-CRITERIA.md section 4.
ALL_CRITERIA = [
    "C1_provenance",
    "C2_dependencies",
    "C3_completeness",
    "C4_buildability",
    "C5_test_coverage",
    "C6_determinism",
    "C7_conformance",
    "C8_security",
    "C9_semantic_conflict",
    "C10_licence",
    "C11_no_proprietary_third_party",
]
APPLICABLE = {
    "IMPLEMENTATION": set(ALL_CRITERIA),
    "SPECIFICATION": {"C1_provenance", "C3_completeness", "C7_conformance",
                      "C9_semantic_conflict", "C10_licence",
                      "C11_no_proprietary_third_party"},
    "TEST": {"C1_provenance", "C2_dependencies", "C3_completeness", "C4_buildability",
             "C6_determinism", "C10_licence"},
    "FIXTURE": {"C1_provenance", "C3_completeness", "C6_determinism", "C10_licence"},
    "EVIDENCE": {"C1_provenance", "C3_completeness", "C8_security", "C10_licence"},
}

# Terminal or holding states and the field each must justify itself with.
REASON_FIELD = {
    "BLOCKED": "blocked_reason",
    "CONFLICT": "conflict_description",
    "REJECTED": "rejected_reason",
    "SUPERSEDED": "superseded_by",
}

BLOCKING_DEPENDENCY = {"BLOCKED", "CONFLICT", "REJECTED"}


def check_register(register: dict, schema: dict, repo_root: Path) -> list[str]:
    """Return every rule violation found. Empty list means the register is valid."""
    errors = jsonschema_mini.validate(register, schema)
    if errors:
        # Rule shape depends on the schema holding; do not compound the noise.
        return errors

    entries = register["entries"]
    by_id: dict[str, dict] = {}

    for entry in entries:
        eid = entry["id"]
        where = f"entry {eid}"

        # Rule 2 -- unique ids.
        if eid in by_id:
            errors.append(f"{where}: duplicate id")
        by_id[eid] = entry

        status = entry["status"]
        prov = entry["provenance"]
        criteria = entry.get("criteria", {})
        history = entry["history"]

        # Rule 3 -- history terminates at the current status.
        if history[-1]["status"] != status:
            errors.append(
                f"{where}: status is {status} but the last history record says "
                f"{history[-1]['status']}"
            )

        # Rule 11 -- terminal and holding states state their reason.
        field = REASON_FIELD.get(status)
        if field and not (entry.get(field) or "").strip():
            errors.append(f"{where}: status {status} requires a non-empty {field!r}")

        # Notes are evidence; an empty note asserts a criterion outcome with nothing
        # behind it.
        for name, criterion in criteria.items():
            if not criterion["note"].strip():
                errors.append(f"{where}: criterion {name} has an empty note")
            if criterion["state"] == "FAIL" and status in ADMITTING:
                errors.append(
                    f"{where}: criterion {name} is FAIL but status is {status}"
                )

        # Rule 13 -- no self-dependency.
        if eid in entry.get("depends_on", []):
            errors.append(f"{where}: depends on itself")

        if status in ADMITTING:
            # Rule 4 -- immutable provenance before approval. A branch is not a commit.
            commit = prov.get("source_commit")
            if not (isinstance(commit, str) and SHA1.match(commit)):
                errors.append(
                    f"{where}: status {status} requires a 40-hex source_commit, got "
                    f"{commit!r}"
                )

            # Rule 5 -- verification precedes approval. This is the rule that stops an
            # artifact being approved because it builds.
            for name in sorted(APPLICABLE[entry["artifact_class"]]):
                state = criteria.get(name, {}).get("state", "NOT_ASSESSED")
                if state not in ("PASS", "NOT_APPLICABLE"):
                    errors.append(
                        f"{where}: status {status} requires criterion {name} to be "
                        f"PASS or NOT_APPLICABLE, found {state}"
                    )

            # Rule 6 -- approval is a decision, recorded separately from verification.
            if "transfer_decision" not in entry:
                errors.append(f"{where}: status {status} requires a transfer_decision")

            # Rule 7 -- derivation is declared.
            if "derivation" not in entry:
                errors.append(f"{where}: status {status} requires derivation")

        if status == "TRANSFERRED":
            # Rule 8 -- transfer is located, and the location is real.
            target = entry.get("target_path")
            if not target:
                errors.append(f"{where}: TRANSFERRED requires target_path")
            elif not (repo_root / target).exists():
                errors.append(f"{where}: target_path {target!r} does not exist")
            if not entry.get("target_commit"):
                errors.append(f"{where}: TRANSFERRED requires target_commit")

            # Rule 9 -- the per-module record exists.
            record = entry.get("record")
            if not record:
                errors.append(f"{where}: TRANSFERRED requires record")
            elif not (repo_root / record).is_file():
                errors.append(f"{where}: record {record!r} does not exist")
            elif not record.startswith(f"{RECORDS_DIR}/"):
                errors.append(f"{where}: record must live under {RECORDS_DIR}/")

            # Rule 10 -- byte-level identity where it matters.
            if entry["artifact_class"] in ("FIXTURE", "EVIDENCE"):
                if not prov.get("source_sha256"):
                    errors.append(
                        f"{where}: TRANSFERRED {entry['artifact_class']} requires "
                        f"source_sha256"
                    )

    # Rule 12 -- dependencies resolve, and do not block.
    for entry in entries:
        for dep in entry.get("depends_on", []):
            if dep not in by_id:
                errors.append(f"entry {entry['id']}: depends_on unknown id {dep!r}")
            elif entry["status"] in ADMITTING and by_id[dep]["status"] in BLOCKING_DEPENDENCY:
                errors.append(
                    f"entry {entry['id']}: status {entry['status']} while dependency "
                    f"{dep} is {by_id[dep]['status']}"
                )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (default: the repository containing this script)",
    )
    args = parser.parse_args(argv)
    root = args.repo_root

    register = json.loads((root / REGISTER).read_text(encoding="utf-8"))
    schema = json.loads((root / SCHEMA).read_text(encoding="utf-8"))

    errors = check_register(register, schema, root)
    if errors:
        print(f"{REGISTER}: {len(errors)} problem(s)", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    count = len(register["entries"])
    reachable = register["corpus_reachable"]
    print(f"{REGISTER}: OK -- {count} entr{'y' if count == 1 else 'ies'}, "
          f"corpus_reachable={reachable}, status_at={register['status_at']}")
    if count == 0 and not reachable:
        print("  note: an empty register with corpus_reachable=false records absence of "
              "observation, not absence of artifacts (see provenance/CORPUS-INDEX.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
