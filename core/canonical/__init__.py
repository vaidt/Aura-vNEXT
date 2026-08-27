"""AURA-CANON/1 -- the canonical byte form of the M0 evidence domain (ADR-0005).

AURA-CANON/1 is a restricted profile of RFC 8785 (JSON Canonicalization Scheme):

  * output is UTF-8 with no insignificant whitespace;
  * object members are sorted by the UTF-16 code-unit sequence of their names;
  * strings are escaped per RFC 8785 section 3.2.2.2 (minimal escaping);
  * numbers are **integers only** -- the profile forbids floating point outright,
    so ECMAScript number formatting never enters the trust boundary;
  * null is forbidden -- an absent optional field is an absent member, which is
    what keeps None distinguishable from Some("").

The restrictions are the point. Every construct RFC 8785 handles with subtlety is
removed from the domain rather than implemented carefully.
"""

from __future__ import annotations

__all__ = [
    "CanonicalisationError",
    "canonicalise",
    "canonical_bytes",
]


class CanonicalisationError(ValueError):
    """A value cannot be represented in AURA-CANON/1.

    Raised rather than approximated: a value that has no canonical form must never
    acquire one by coercion, because the digest would then bind something other than
    what the caller supplied.
    """


# RFC 8785 section 3.2.2.2 -- the two-character escapes, in preference to \u00xx.
_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def _escape_string(value: str) -> str:
    out = ['"']
    for char in value:
        code = ord(char)
        short = _SHORT_ESCAPES.get(code)
        if short is not None:
            out.append(short)
        elif code < 0x20:
            # Remaining C0 controls have no short form and are emitted as \u00xx.
            out.append(f"\\u{code:04x}")
        else:
            # Everything else -- including U+007F, pipes, and all non-ASCII -- is
            # emitted literally and carried by the UTF-8 encoding of the result.
            out.append(char)
    out.append('"')
    return "".join(out)


def _member_sort_key(name: str) -> bytes:
    """Sort key reproducing RFC 8785's UTF-16 code-unit ordering.

    Comparing UTF-16BE byte strings is exactly comparing UTF-16 code-unit sequences,
    which differs from code-point order above the BMP: an astral character encodes to
    a lead surrogate in U+D800..U+DBFF and therefore sorts before U+E000..U+FFFF.
    Sorting Python strings directly would order those the other way round.
    """
    return name.encode("utf-16-be")


def canonicalise(value) -> str:
    """Return the AURA-CANON/1 text of ``value``.

    Accepts only the M0 value space: dict with string keys, list, str, bool, and int.
    """
    return "".join(_emit(value, []))


def _emit(value, path: list[str]) -> list[str]:
    where = "/".join(path) or "<root>"

    # bool is a subclass of int in Python; it must be tested first or True would
    # canonicalise as the integer 1.
    if isinstance(value, bool):
        return ["true" if value else "false"]

    if isinstance(value, int):
        return [str(value)]

    if isinstance(value, str):
        return [_escape_string(value)]

    if isinstance(value, dict):
        parts = ["{"]
        first = True
        for name in sorted(value, key=_member_sort_key):
            if not isinstance(name, str):
                raise CanonicalisationError(
                    f"at {where}: member name {name!r} is not a string"
                )
            if not first:
                parts.append(",")
            first = False
            parts.append(_escape_string(name))
            parts.append(":")
            parts.extend(_emit(value[name], path + [name]))
        parts.append("}")
        return parts

    if isinstance(value, (list, tuple)):
        parts = ["["]
        for index, item in enumerate(value):
            if index:
                parts.append(",")
            parts.extend(_emit(item, path + [str(index)]))
        parts.append("]")
        return parts

    if value is None:
        raise CanonicalisationError(
            f"at {where}: null is not representable in AURA-CANON/1; omit the member "
            f"instead, so that an absent value stays distinct from an empty one"
        )

    if isinstance(value, float):
        raise CanonicalisationError(
            f"at {where}: floating point is not representable in AURA-CANON/1; "
            f"convert to an integer with a declared scale (see core.models.confidence)"
        )

    raise CanonicalisationError(f"at {where}: {type(value).__name__} is not representable")


def canonical_bytes(value) -> bytes:
    """Return the canonical UTF-8 bytes of ``value`` -- the sole hash preimage."""
    return canonicalise(value).encode("utf-8")
