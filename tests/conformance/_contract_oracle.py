"""An independent implementation of AURA-CANON/1, written from the contract text.

This module exists to break the circularity in the P0-02 oracle. The committed
vectors were produced by ``core.canonical``; comparing them back to
``core.canonical`` proves only that the encoder has not changed, never that it was
right in the first place.

This is a second implementation, derived from
``docs/contract/M0-EVIDENCE-CONTRACT.md`` sections 3 and 4 and from RFC 8785
section 3.2.2.2 -- not from ``core/canonical/__init__.py``. It deliberately differs
in structure and in mechanism:

  * member ordering derives UTF-16 code units arithmetically, by splitting
    astral code points into surrogate pairs by hand, rather than calling
    ``str.encode("utf-16-be")``. A shared bug in the codec approach cannot hide
    in both.
  * escaping is table-driven from the contract's list, built independently.
  * the walk is a single recursive function returning str, not a parts list.

It is not a drop-in replacement and is not used by the product. It is a test
oracle, and if the two implementations ever disagree, one of them is wrong and the
committed vectors say which.
"""

from __future__ import annotations

__all__ = ["OracleRejection", "canonicalise_from_contract", "utf16_code_units"]


class OracleRejection(Exception):
    """The oracle refuses a value the contract says has no canonical form."""


# Contract section 3 / RFC 8785 section 3.2.2.2, transcribed from the specification
# text rather than copied from the implementation.
_TWO_CHARACTER_ESCAPES = {
    0x22: '\\"',      # quotation mark
    0x5C: "\\\\",     # reverse solidus
    0x08: "\\b",      # backspace
    0x09: "\\t",      # tab
    0x0A: "\\n",      # line feed
    0x0C: "\\f",      # form feed
    0x0D: "\\r",      # carriage return
}


def utf16_code_units(text: str) -> tuple[int, ...]:
    """Return the UTF-16 code unit sequence of ``text``, computed arithmetically.

    A code point below U+10000 is one unit. Above that it is a surrogate pair:
    subtract 0x10000, the high ten bits give a lead unit in U+D800..U+DBFF and the
    low ten bits a trail unit in U+DC00..U+DFFF.

    This is why the ordering differs from code-point order: an astral character
    leads with a unit in the D800 block, which sorts below U+E000..U+FFFF.
    """
    units: list[int] = []
    for character in text:
        code = ord(character)
        if 0xD800 <= code <= 0xDFFF:
            raise OracleRejection(f"lone surrogate U+{code:04X} has no encoding")
        if code < 0x10000:
            units.append(code)
        else:
            offset = code - 0x10000
            units.append(0xD800 + (offset >> 10))
            units.append(0xDC00 + (offset & 0x3FF))
    return tuple(units)


def _string(text: str) -> str:
    out = '"'
    for character in text:
        code = ord(character)
        if 0xD800 <= code <= 0xDFFF:
            raise OracleRejection(f"lone surrogate U+{code:04X} has no encoding")
        if code in _TWO_CHARACTER_ESCAPES:
            out += _TWO_CHARACTER_ESCAPES[code]
        elif code < 0x20:
            out += "\\u%04x" % code
        else:
            out += character
    return out + '"'


def canonicalise_from_contract(value) -> str:
    """Return the AURA-CANON/1 text of ``value`` per the contract."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, list):
        return "[" + ",".join(canonicalise_from_contract(item) for item in value) + "]"
    if isinstance(value, dict):
        names = sorted(value, key=utf16_code_units)
        return "{" + ",".join(
            _string(name) + ":" + canonicalise_from_contract(value[name])
            for name in names
        ) + "}"
    if value is None:
        raise OracleRejection("null is not representable; omit the member instead")
    if isinstance(value, float):
        raise OracleRejection("floating point is not representable")
    raise OracleRejection(f"{type(value).__name__} is not representable")
