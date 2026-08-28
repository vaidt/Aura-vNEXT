"""Repository structure and governance invariants (ADR-0001, ADR-0003)."""

import json
import unittest
from pathlib import Path

from _support import REPO_ROOT, load_schema

import validate_structure


class StructureTest(unittest.TestCase):
    def test_repository_structure_is_valid(self):
        errors = validate_structure.check_structure(REPO_ROOT)
        self.assertEqual([], errors, "\n".join(errors))

    def test_every_reserved_directory_is_declared_in_adr_0003(self):
        adr = (REPO_ROOT / "architecture/decisions/ADR-0003-repository-layout.md").read_text(
            encoding="utf-8"
        )
        for name in validate_structure.RESERVED_DIRS:
            with self.subTest(directory=name):
                self.assertIn(f"{name}/", adr)

    def test_every_m0_directory_is_declared_in_adr_0006(self):
        """A directory not named by the ADR that added it is an undeclared decision."""
        adr = (REPO_ROOT / "architecture/decisions"
               / "ADR-0006-m0-evidence-package-and-verifier.md").read_text(encoding="utf-8")
        for name in validate_structure.M0_DIRS:
            with self.subTest(directory=name):
                self.assertIn(f"{name}/", adr)

    def test_still_reserved_directories_hold_no_implementation(self):
        """ADR-0006 admitted M0 into core/ and app/ and nowhere else.

        The Genesis form of this test covered every domain directory. ADR-0006 narrowed
        it by decision rather than by weakening it: the directories M0 did not touch are
        still asserted empty, so M0 cannot sprawl into modules whose language, design,
        and acceptance criteria have not been decided.
        """
        errors = validate_structure.check_reserved_dirs_are_empty(REPO_ROOT)
        self.assertEqual([], errors, "\n".join(errors))

    def test_reserved_emptiness_check_actually_detects_implementation(self):
        """The guard must fail when the thing it guards against is present."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / "runtime").mkdir()
            (fake / "runtime" / "enforcer.py").write_text("x = 1", encoding="utf-8")
            self.assertTrue(validate_structure.check_reserved_dirs_are_empty(fake))

    def test_m0_implementation_stays_inside_the_m0_boundary(self):
        """ADR-0006 section 5: M0 names none of the excluded concerns."""
        errors = validate_structure.check_m0_scope(REPO_ROOT)
        self.assertEqual([], errors, "\n".join(errors))

    def test_m0_scope_check_actually_detects_an_excursion(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            (fake / "core").mkdir()
            (fake / "core" / "x.py").write_text("# merkle tree sealing", encoding="utf-8")
            self.assertTrue(validate_structure.check_m0_scope(fake))

    def test_no_frozen_corpus_wired_into_git(self):
        self.assertEqual([], validate_structure.check_git_boundary(REPO_ROOT))

    def test_adr_index_and_directory_agree(self):
        self.assertEqual([], validate_structure.check_adr_index(REPO_ROOT))

    def test_missing_reserved_directory_is_detected(self):
        """The structure check must actually fail when the structure is wrong."""
        errors = validate_structure.check_structure(REPO_ROOT / "governance")
        self.assertTrue(errors, "check_structure passed against a non-repository root")


class GovernanceDocumentTest(unittest.TestCase):
    NORMATIVE = [
        "governance/GENESIS.md",
        "governance/REPOSITORY-BOUNDARY.md",
        "governance/MODULE-ACCEPTANCE-CRITERIA.md",
        "governance/DEVELOPMENT-RULES.md",
        "provenance/PROVENANCE-POLICY.md",
        "provenance/TRANSFER-REGISTER.md",
    ]

    def test_normative_documents_declare_their_status(self):
        for doc in self.NORMATIVE:
            with self.subTest(document=doc):
                text = (REPO_ROOT / doc).read_text(encoding="utf-8")
                self.assertIn("**Document status:** NORMATIVE", text)

    def test_product_direction_is_non_normative(self):
        text = (REPO_ROOT / "architecture/PRODUCT-DIRECTION.md").read_text(encoding="utf-8")
        self.assertIn("**Document status:** NON-NORMATIVE", text)
        self.assertIn("does not authorise implementation", text)

    def test_every_transfer_status_is_defined_in_the_criteria(self):
        """The schema's status vocabulary and the normative definitions must not drift."""
        schema = load_schema()
        criteria = (REPO_ROOT / "governance/MODULE-ACCEPTANCE-CRITERIA.md").read_text(
            encoding="utf-8"
        )
        for status in schema["$defs"]["status"]["enum"]:
            with self.subTest(status=status):
                self.assertIn(f"`{status}`", criteria)

    def test_no_licence_is_claimed_while_the_question_is_open(self):
        """OQ-3 is open. A LICENSE file would answer it by default rather than by decision."""
        open_questions = (REPO_ROOT / "governance/OPEN-QUESTIONS.md").read_text(
            encoding="utf-8"
        )
        if "OQ-3" in open_questions and "Licence and rights model" in open_questions:
            for name in ("LICENSE", "LICENSE.md", "LICENCE", "LICENCE.md", "COPYING"):
                self.assertFalse(
                    (REPO_ROOT / name).exists(),
                    f"{name} exists while OQ-3 is recorded as open",
                )


class RegisterStateTest(unittest.TestCase):
    def test_genesis_register_claims_no_transfer(self):
        register = json.loads(
            (REPO_ROOT / "provenance/transfer-register.json").read_text(encoding="utf-8")
        )
        transferred = [e["id"] for e in register["entries"] if e["status"] == "TRANSFERRED"]
        self.assertEqual(
            [], transferred,
            "the register claims transferred artifacts; each needs a provenance record "
            "and this assertion updating",
        )


if __name__ == "__main__":
    unittest.main()
