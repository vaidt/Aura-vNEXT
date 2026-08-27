#!/usr/bin/env python3
"""Validate the Aura vNEXT repository structure and governance invariants.

Checks that the reserved layout of ADR-0003 is intact, that the normative governance
documents exist, that the ADR index and the ADR directory agree, and that no Git
configuration violates the repository boundary (ADR-0001).

Standard library only (ADR-0002).

Usage:
    python3 tools/validate_structure.py [--repo-root PATH]
Exit status 0 when the structure is valid, 1 otherwise.
"""

from __future__ import annotations

import argparse
import configparser
import re
import sys
from pathlib import Path

# ADR-0003 -- reserved by domain, each carrying a README stating its purpose.
RESERVED_DIRS = [
    "architecture", "governance", "provenance", "conformance", "core", "runtime",
    "policy", "audit", "evidence", "integrations", "packs", "cli", "tests", "tools",
    "docs",
]

REQUIRED_DOCS = [
    "README.md",
    "CONTRIBUTING.md",
    "governance/GENESIS.md",
    "governance/REPOSITORY-BOUNDARY.md",
    "governance/MODULE-ACCEPTANCE-CRITERIA.md",
    "governance/DEVELOPMENT-RULES.md",
    "governance/OPEN-QUESTIONS.md",
    "provenance/PROVENANCE-POLICY.md",
    "provenance/TRANSFER-REGISTER.md",
    "provenance/CORPUS-INDEX.md",
    "provenance/BOUNDARY-INCIDENTS.md",
    "provenance/transfer-register.json",
    "provenance/transfer-register.schema.json",
    "architecture/PRODUCT-DIRECTION.md",
    "architecture/decisions/README.md",
    "architecture/decisions/ADR-0001-new-canonical-repository.md",
]

ADR_DIR = Path("architecture/decisions")
ADR_FILE = re.compile(r"^ADR-(\d{4})-[a-z0-9-]+\.md$")

# ADR-0001 section 3: no frozen repository may be a remote, submodule, or subtree here.
FORBIDDEN_REMOTE = re.compile(r"aura[-_]?idtoken", re.IGNORECASE)


def check_structure(root: Path) -> list[str]:
    errors: list[str] = []

    for name in RESERVED_DIRS:
        directory = root / name
        if not directory.is_dir():
            errors.append(f"reserved directory {name}/ is missing (ADR-0003)")
        elif not (directory / "README.md").is_file():
            errors.append(f"{name}/ has no README.md stating its purpose (ADR-0003)")

    for doc in REQUIRED_DOCS:
        if not (root / doc).is_file():
            errors.append(f"required document {doc} is missing")

    errors += check_adr_index(root)
    errors += check_git_boundary(root)
    return errors


def check_adr_index(root: Path) -> list[str]:
    """The index and the directory must agree; an unindexed ADR is an invisible decision."""
    errors: list[str] = []
    adr_dir = root / ADR_DIR
    index_path = adr_dir / "README.md"
    if not index_path.is_file():
        return [f"{ADR_DIR}/README.md is missing"]

    index = index_path.read_text(encoding="utf-8")
    numbers: set[str] = set()

    for path in sorted(adr_dir.iterdir()):
        if path.name == "README.md" or not path.is_file():
            continue
        match = ADR_FILE.match(path.name)
        if not match:
            errors.append(f"{ADR_DIR}/{path.name}: name must match ADR-NNNN-slug.md")
            continue
        if match.group(1) in numbers:
            errors.append(f"{ADR_DIR}/{path.name}: ADR number reused")
        numbers.add(match.group(1))
        if path.name not in index:
            errors.append(f"{ADR_DIR}/{path.name} is not listed in the ADR index")
        if not re.search(r"^- \*\*Status:\*\* ", path.read_text(encoding="utf-8"), re.M):
            errors.append(f"{ADR_DIR}/{path.name}: no Status line")

    for linked in re.findall(r"\(([Aa][Dd][Rr]-\d{4}-[a-z0-9-]+\.md)\)", index):
        if not (adr_dir / linked).is_file():
            errors.append(f"ADR index links {linked}, which does not exist")

    return errors


def check_git_boundary(root: Path) -> list[str]:
    """No frozen source repository may be wired into this repository's Git plumbing."""
    errors: list[str] = []

    if (root / ".gitmodules").exists():
        errors.append(".gitmodules exists: submodules are prohibited by ADR-0001 section 3")

    config_path = root / ".git" / "config"
    if config_path.is_file():
        parser = configparser.ConfigParser(strict=False)
        try:
            parser.read_string(config_path.read_text(encoding="utf-8"))
        except configparser.Error:
            return errors  # unreadable git config is not this check's business
        for section in parser.sections():
            if not section.startswith("remote "):
                continue
            url = parser.get(section, "url", fallback="")
            if FORBIDDEN_REMOTE.search(url):
                errors.append(
                    f"git remote {section} points at a frozen source repository "
                    f"({url}): prohibited by ADR-0001 section 3"
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

    errors = check_structure(args.repo_root)
    if errors:
        print(f"repository structure: {len(errors)} problem(s)", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(f"repository structure: OK -- {len(RESERVED_DIRS)} reserved directories, "
          f"{len(REQUIRED_DOCS)} required documents")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
