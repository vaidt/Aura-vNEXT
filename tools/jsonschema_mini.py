"""A deliberately small JSON Schema validator.

Supports exactly the draft 2020-12 subset used by
``provenance/transfer-register.schema.json`` and nothing more. Standard library only,
per ADR-0002 (no dependency policy has been decided -- see OPEN-QUESTIONS OQ-4).

An unsupported keyword is a hard error rather than a silent pass: a validator that
quietly ignores a constraint is worse than no validator, because the build goes green
and the constraint is not enforced.
"""

from __future__ import annotations

import re

SUPPORTED = {
    # structural / annotation-only, ignored during validation
    "$schema", "$id", "$defs", "title", "description", "examples", "default",
    # validated
    "$ref", "type", "enum", "const", "properties", "required",
    "additionalProperties", "items", "minItems", "minLength", "pattern", "anyOf",
}

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "integer": int,
    "null": type(None),
}


class SchemaError(Exception):
    """The schema itself uses something this validator does not implement."""


def _is_type(value, name: str) -> bool:
    if name not in _TYPES:
        raise SchemaError(f"unsupported type {name!r}")
    if name in ("number", "integer") and isinstance(value, bool):
        return False  # bool is an int in Python; JSON says otherwise
    if name == "boolean":
        return isinstance(value, bool)
    return isinstance(value, _TYPES[name])


def _resolve(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise SchemaError(f"only local refs are supported, got {ref!r}")
    node = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            raise SchemaError(f"unresolvable ref {ref!r}")
        node = node[part]
    return node


def validate(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Return a list of human-readable error strings; empty means valid."""
    root = schema if root is None else root
    errors: list[str] = []

    unsupported = set(schema) - SUPPORTED
    if unsupported:
        raise SchemaError(f"{path}: unsupported schema keywords {sorted(unsupported)}")

    if "$ref" in schema:
        return validate(instance, _resolve(schema["$ref"], root), root, path)

    if "type" in schema:
        names = schema["type"]
        names = [names] if isinstance(names, str) else names
        if not any(_is_type(instance, n) for n in names):
            errors.append(f"{path}: expected type {'|'.join(names)}, got {type(instance).__name__}")
            return errors  # further checks would be noise

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected {schema['const']!r}")

    if "anyOf" in schema:
        if all(validate(instance, sub, root, path) for sub in schema["anyOf"]):
            errors.append(f"{path}: {instance!r} matches none of the permitted forms")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], root, f"{path}[{i}]")

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}: missing required property {name!r}")
        if schema.get("additionalProperties") is False:
            for name in instance:
                if name not in props:
                    errors.append(f"{path}: unexpected property {name!r}")
        elif "additionalProperties" in schema:
            raise SchemaError(f"{path}: only additionalProperties=false is supported")
        for name, value in instance.items():
            if name in props:
                errors += validate(value, props[name], root, f"{path}.{name}")

    return errors
