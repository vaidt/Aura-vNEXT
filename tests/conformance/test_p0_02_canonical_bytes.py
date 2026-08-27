"""P0-02 -- exact canonical-byte contract.

The gate is the *bytes*, not the digest. A suite that checked only digests would pass
against an encoder that was wrong in a way the vectors happened not to reach, and
would give a second implementer nothing to diff against. Every assertion here is made
against the recorded byte string.
"""

import unittest

from _m0 import build_entry, load_vectors, vectors_by_name

from core.chain import entry_preimage


class CanonicalByteVectorTest(unittest.TestCase):
    def test_every_vector_reproduces_its_recorded_bytes(self):
        for vector in load_vectors():
            with self.subTest(vector=vector["name"]):
                produced = entry_preimage(build_entry(vector["input"]))
                self.assertEqual(
                    bytes.fromhex(vector["canonical_hex"]), produced,
                    f"{vector['name']}: canonical bytes differ from the recorded vector",
                )
                self.assertEqual(vector["canonical_utf8"], produced.decode("utf-8"))
                self.assertEqual(vector["canonical_length"], len(produced))

    def test_recorded_utf8_and_hex_agree(self):
        """The two recordings of the same bytes must not drift apart."""
        for vector in load_vectors():
            with self.subTest(vector=vector["name"]):
                self.assertEqual(
                    vector["canonical_utf8"].encode("utf-8"),
                    bytes.fromhex(vector["canonical_hex"]),
                )

    def test_no_two_vectors_share_canonical_bytes(self):
        """Distinct fixtures must stay distinct, or a vector silently tests nothing."""
        seen: dict[bytes, str] = {}
        for vector in load_vectors():
            produced = entry_preimage(build_entry(vector["input"]))
            if produced in seen:
                self.fail(
                    f"{vector['name']} and {seen[produced]} canonicalise identically"
                )
            seen[produced] = vector["name"]

    def test_integrity_value_is_absent_from_its_own_preimage(self):
        """H(canonical(entry without integrity hash)), never H(canonical(entry)).

        Checked on the bytes rather than on the representation dict, because the
        property that matters is what was hashed.
        """
        for vector in load_vectors():
            with self.subTest(vector=vector["name"]):
                produced = entry_preimage(build_entry(vector["input"]))
                self.assertNotIn(b'"entry_hash"', produced)


class ByteLevelPropertyTest(unittest.TestCase):
    """Each property the M0 contract requires, asserted against the exact bytes."""

    def setUp(self):
        self.vectors = vectors_by_name()

    def canonical(self, name: str) -> bytes:
        return bytes.fromhex(self.vectors[name]["canonical_hex"])

    def test_unicode_is_emitted_literally_as_utf8(self):
        produced = self.canonical("unicode-bmp")
        self.assertIn("\u4e2d\u6587".encode("utf-8"), produced)
        self.assertNotIn(b"\\u4e2d", produced)

    def test_astral_member_names_sort_by_utf16_code_unit(self):
        """RFC 8785 orders names by UTF-16 code units, not by code point.

        U+1F510 encodes to the lead surrogate U+D83D, which sorts *before* U+FFFD.
        Sorting Python strings directly would place it after, so this vector fails
        against a naive implementation.
        """
        text = self.canonical("unicode-astral").decode("utf-8")
        metadata = text.split('"metadata":{', 1)[1]
        self.assertLess(
            metadata.index("\U0001F510key"), metadata.index("\uFFFDkey"),
            "astral member name must sort before U+FFFD under UTF-16 ordering",
        )
        self.assertLess(metadata.index("zkey"), metadata.index("\U0001F510key"))

    def test_quotes_escape_and_do_not_terminate_a_string(self):
        self.assertIn(b'he said \\"deny\\" loudly', self.canonical("quotes"))

    def test_backslashes_are_doubled(self):
        produced = self.canonical("backslashes")
        self.assertIn(b'"C:\\\\policies\\\\loan\\\\"', produced)

    def test_control_characters_take_the_specified_escapes(self):
        produced = self.canonical("control-characters")
        for expected in (b"\\r", b"\\n", b"\\t", b"\\u0000", b"\\u001f",
                         b"\\b", b"\\f", b"\\u000b"):
            self.assertIn(expected, produced)
        for raw in (b"\r", b"\n", b"\t", b"\x00"):
            self.assertNotIn(raw, produced, "a raw control byte reached the preimage")

    def test_pipes_are_content_and_never_delimiters(self):
        produced = self.canonical("pipes")
        self.assertIn(b'"a|b||c|"', produced)
        self.assertNotIn(b"\\|", produced)

    def test_literal_none_text_is_content(self):
        self.assertIn(b'"policy_repr":"None"', self.canonical("literal-text-None"))

    def test_literal_some_empty_text_is_content(self):
        self.assertIn(
            b'"policy_repr":"Some(\\"\\")"', self.canonical("literal-text-Some-empty")
        )

    def test_absent_optional_is_not_null_and_not_empty(self):
        """None, Some(""), and Some(value) are three distinct byte strings."""
        absent = self.canonical("optional-absent")
        present = self.canonical("optional-present")
        self.assertNotIn(b"shadow_hash", absent)
        self.assertNotIn(b"null", absent)
        self.assertIn(b'"shadow_hash":"', present)
        self.assertNotEqual(absent, present)

    def test_absent_metadata_key_differs_from_empty_metadata_value(self):
        absent = self.canonical("metadata-key-absent")
        empty = self.canonical("metadata-key-empty")
        self.assertNotEqual(absent, empty)
        self.assertNotIn(b'"opt"', absent)
        self.assertIn(b'"opt":""', empty)

    def test_empty_violation_array_is_present_as_a_member(self):
        self.assertIn(b'"violations":[]', self.canonical("violations-empty"))

    def test_violation_ordering_is_protected(self):
        ab = self.canonical("violations-ordered-ab")
        ba = self.canonical("violations-ordered-ba")
        self.assertNotEqual(ab, ba, "reordering violations must change the bytes")
        self.assertLess(ab.index(b"RULE.A"), ab.index(b"RULE.B"))
        self.assertLess(ba.index(b"RULE.B"), ba.index(b"RULE.A"))

    def test_confidence_appears_as_integer_basis_points(self):
        produced = self.canonical("confidence-boundaries")
        for expected in (b'"confidence":0', b'"confidence":5000',
                         b'"confidence":9500', b'"confidence":10000'):
            self.assertIn(expected, produced)
        self.assertNotIn(b"0.95", produced, "a float reached the preimage")
        self.assertNotIn(b"e-", produced, "exponent notation reached the preimage")

    def test_protected_metadata_participates_in_the_preimage(self):
        self.assertIn(b'"metadata":{"actor":"agent-17"', self.canonical("complete"))

    def test_injection_shaped_content_cannot_restructure_the_preimage(self):
        """Content that looks like canonical syntax stays inside its string."""
        produced = self.canonical("injection-shaped-content")
        self.assertIn(b'\\",\\"entry_hash\\":\\"deadbeef', produced)
        self.assertNotIn(b'"entry_hash"', produced)
        self.assertNotIn(b'"seq":99', produced)


if __name__ == "__main__":
    unittest.main()
