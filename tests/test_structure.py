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

    def test_reserved_directories_hold_no_implementation(self):
        """Genesis admits process, not product. A source file here means something was
        added without passing the transfer gate, or scaffolding was introduced."""
        product_dirs = ["core", "runtime", "policy", "audit", "evidence",
                        "integrations", "packs", "cli", "conformance"]
        suffixes = {".py", ".ts", ".js", ".go", ".rs", ".java", ".rb", ".c", ".h",
                    ".cpp", ".cs", ".kt", ".swift"}
        offenders = [
            str(path.relative_to(REPO_ROOT))
            for name in product_dirs
            for path in (REPO_ROOT / name).rglob("*")
            if path.is_file() and path.suffix in suffixes
        ]
        self.assertEqual(
            [], offenders,
            "implementation found in a reserved directory during Genesis; "
            "see governance/REPOSITORY-BOUNDARY.md section 4:\n" + "\n".join(offenders),
        )

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
