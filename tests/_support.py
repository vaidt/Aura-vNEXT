"""Shared test helpers. Adds tools/ to the import path and locates the repository root."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))


def load_schema() -> dict:
    return json.loads(
        (REPO_ROOT / "provenance/transfer-register.schema.json").read_text(encoding="utf-8")
    )


def load_register() -> dict:
    return json.loads(
        (REPO_ROOT / "provenance/transfer-register.json").read_text(encoding="utf-8")
    )
