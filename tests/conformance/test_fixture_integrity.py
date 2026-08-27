"""The committed fixtures must match the implementation, and must cover the contract.

Without this, a change to the encoder could be "fixed" by regenerating the vectors,
and the vectors would stop being a contract and become a snapshot of whatever the
code currently does.
"""

import json
import unittest

from _m0 import REFERENCE_PACKAGE, VECTORS_PATH, load_vectors

import build_m0_fixtures


class FixtureDriftTest(unittest.TestCase):
    def test_committed_fixtures_match_the_implementation(self):
        """Fails if the vectors or the reference package were not regenerated.

        A failure here is a prompt to decide, not to regenerate: changing the recorded
        bytes is a breaking change to the canonical form (contract section 9).
        """
        self.assertEqual(
            0, build_m0_fixtures.main(["--check"]),
            "committed fixtures differ from the implementation; if the canonical form "
            "genuinely changed, that needs a superseding ADR and a new form identifier",
        )

    def test_vector_file_declares_its_authority_and_makes_no_compatibility_claim(self):
        data = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
        self.assertEqual("AURA-CANON/1", data["canonical_form"])
        self.assertEqual("SHA-256", data["digest"])
        self.assertIn("ADR-0005", data["authority"])
        self.assertIn("NOT", data["authority"])

    def test_every_vector_states_its_purpose(self):
        for vector in load_vectors():
            with self.subTest(vector=vector["name"]):
                self.assertTrue(vector["purpose"].strip(),
                                "a vector with no stated purpose cannot be reviewed")

    def test_vectors_cover_every_property_the_contract_requires(self):
        required = {
            "complete", "unicode-bmp", "unicode-astral", "quotes", "backslashes",
            "control-characters", "pipes", "literal-text-None",
            "literal-text-Some-empty", "optional-absent", "optional-present",
            "metadata-key-absent", "metadata-key-empty", "violations-empty",
            "violations-ordered-ab", "violations-ordered-ba", "confidence-boundaries",
            "injection-shaped-content",
        }
        present = {vector["name"] for vector in load_vectors()}
        self.assertEqual(set(), required - present,
                         f"contract properties with no vector: {required - present}")


class ReferencePackageTest(unittest.TestCase):
    def test_package_has_the_layout_the_contract_specifies(self):
        for relative in ("manifest.json", "evidence/audit.jsonl", "evidence/policy.json",
                         "evidence/genesis.json", "expected/result.json", "README.md"):
            with self.subTest(path=relative):
                self.assertTrue((REFERENCE_PACKAGE / relative).is_file(),
                                f"{relative} missing from the reference package")

    def test_manifest_digests_match_the_files_on_disk(self):
        import hashlib

        manifest = json.loads(
            (REFERENCE_PACKAGE / "manifest.json").read_text(encoding="utf-8")
        )
        for relative, expected in manifest["files"].items():
            with self.subTest(path=relative):
                actual = hashlib.sha256(
                    (REFERENCE_PACKAGE / relative).read_bytes()
                ).hexdigest()
                self.assertEqual(expected, actual)

    def test_package_carries_more_than_one_chained_record(self):
        """A single-record package would not exercise chain linkage at all."""
        text = (REFERENCE_PACKAGE / "evidence/audit.jsonl").read_text(encoding="utf-8")
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        self.assertGreaterEqual(len(records), 3)
        for index, record in enumerate(records[1:], start=1):
            self.assertEqual(records[index - 1]["entry_hash"], record["prev_hash"])


if __name__ == "__main__":
    unittest.main()
