"""Transfer register validation, and proof that the validator enforces what it claims.

The register being valid is the easy half. The half that matters is that the validator
would reject a register that broke the rules in provenance/TRANSFER-REGISTER.md section 4.
A validator that passes everything leaves a green build and no enforcement.
"""

import copy
import unittest

from _support import REPO_ROOT, load_register, load_schema

import jsonschema_mini
import validate_register


VALID_TRANSFERRED = {
    "id": "TR-9999",
    "title": "Synthetic entry used only by the validator's own tests",
    "artifact_class": "IMPLEMENTATION",
    "status": "TRANSFERRED",
    "derivation": "ADAPTED",
    "provenance": {
        "source_repository": "example/frozen-corpus",
        "source_path": "src/example.ext",
        "source_ref": "main",
        "source_commit": "0" * 40,
        "source_version": None,
        "original_tests": ["test/example_test.ext"],
        "required_fixtures": [],
        "dependencies": [],
    },
    "criteria": {
        name: {"state": "PASS", "note": "synthetic"}
        for name in validate_register.ALL_CRITERIA
    },
    "transfer_decision": {
        "decided_by": "synthetic",
        "decided_on": "2026-08-27",
        "reference": "architecture/decisions/ADR-0001-new-canonical-repository.md",
    },
    "target_path": "README.md",
    "target_commit": "synthetic",
    "record": "provenance/records/README.md",
    "history": [
        {"date": "2026-08-27", "status": "TRANSFERRED", "reason": "synthetic"},
    ],
}


def register_with(*entries) -> dict:
    return {
        "register_version": "1.0.0",
        "status_at": "2026-08-27",
        "corpus_reachable": True,
        "entries": [copy.deepcopy(e) for e in entries],
    }


class ActualRegisterTest(unittest.TestCase):
    def test_register_is_valid(self):
        errors = validate_register.check_register(
            load_register(), load_schema(), REPO_ROOT
        )
        self.assertEqual([], errors, "\n".join(errors))

    def test_empty_register_records_unreachable_corpus(self):
        """An empty register is only honest if it says why it is empty."""
        register = load_register()
        if not register["entries"]:
            self.assertFalse(
                register["corpus_reachable"],
                "register is empty but claims the corpus was reachable, which would "
                "assert the corpus holds nothing worth recording",
            )


class ValidatorRejectionTest(unittest.TestCase):
    """Each test breaks exactly one rule and asserts the validator notices."""

    def assert_rejected(self, entry, fragment):
        errors = validate_register.check_register(
            register_with(entry), load_schema(), REPO_ROOT
        )
        joined = "\n".join(errors)
        self.assertTrue(errors, "validator accepted an invalid register")
        self.assertIn(fragment, joined)

    def test_baseline_entry_is_accepted(self):
        errors = validate_register.check_register(
            register_with(VALID_TRANSFERRED), load_schema(), REPO_ROOT
        )
        self.assertEqual([], errors, "\n".join(errors))

    def test_rule2_duplicate_id_rejected(self):
        errors = validate_register.check_register(
            register_with(VALID_TRANSFERRED, VALID_TRANSFERRED), load_schema(), REPO_ROOT
        )
        self.assertIn("duplicate id", "\n".join(errors))

    def test_rule3_history_must_terminate_at_current_status(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["history"][-1]["status"] = "VERIFIED"
        self.assert_rejected(entry, "last history record")

    def test_rule4_branch_name_is_not_a_commit(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["provenance"]["source_commit"] = None
        self.assert_rejected(entry, "40-hex source_commit")

    def test_rule5_unassessed_criterion_blocks_approval(self):
        """The core rule: buildable is not approved."""
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["criteria"] = {
            "C4_buildability": {"state": "PASS", "note": "it compiles"},
        }
        errors = validate_register.check_register(
            register_with(entry), load_schema(), REPO_ROOT
        )
        joined = "\n".join(errors)
        for name in validate_register.ALL_CRITERIA:
            if name != "C4_buildability":
                self.assertIn(name, joined)

    def test_rule5_applies_per_artifact_class(self):
        """A SPECIFICATION is not held to criteria that cannot apply to it."""
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["artifact_class"] = "SPECIFICATION"
        entry["derivation"] = "SPECIFICATION_ONLY"
        entry["criteria"] = {
            name: {"state": "PASS", "note": "synthetic"}
            for name in validate_register.APPLICABLE["SPECIFICATION"]
        }
        errors = validate_register.check_register(
            register_with(entry), load_schema(), REPO_ROOT
        )
        self.assertEqual([], errors, "\n".join(errors))

    def test_failed_criterion_blocks_approval(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["criteria"]["C8_security"] = {"state": "FAIL", "note": "unreviewed crypto"}
        self.assert_rejected(entry, "C8_security is FAIL")

    def test_empty_criterion_note_rejected(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["criteria"]["C3_completeness"] = {"state": "NOT_APPLICABLE", "note": "  "}
        self.assert_rejected(entry, "empty note")

    def test_rule6_approval_requires_a_recorded_decision(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        del entry["transfer_decision"]
        self.assert_rejected(entry, "requires a transfer_decision")

    def test_rule7_derivation_must_be_declared(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        del entry["derivation"]
        self.assert_rejected(entry, "requires derivation")

    def test_rule8_target_path_must_exist(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["target_path"] = "core/does-not-exist.ext"
        self.assert_rejected(entry, "does not exist")

    def test_rule9_transferred_requires_an_existing_record(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["record"] = "provenance/records/TR-9999.md"
        self.assert_rejected(entry, "does not exist")

    def test_rule10_transferred_fixture_requires_source_sha256(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["artifact_class"] = "FIXTURE"
        entry["derivation"] = "VERBATIM"
        entry["criteria"] = {
            name: {"state": "PASS", "note": "synthetic"}
            for name in validate_register.APPLICABLE["FIXTURE"]
        }
        self.assert_rejected(entry, "requires source_sha256")

    def test_rule11_blocked_requires_a_reason(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["status"] = "BLOCKED"
        entry["history"][-1]["status"] = "BLOCKED"
        self.assert_rejected(entry, "'blocked_reason'")

    def test_rule11_conflict_requires_a_description(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["status"] = "CONFLICT"
        entry["history"][-1]["status"] = "CONFLICT"
        self.assert_rejected(entry, "'conflict_description'")

    def test_rule12_unknown_dependency_rejected(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["depends_on"] = ["TR-0404"]
        self.assert_rejected(entry, "unknown id")

    def test_rule12_blocked_dependency_prevents_approval(self):
        blocker = copy.deepcopy(VALID_TRANSFERRED)
        blocker["id"] = "TR-9998"
        blocker["status"] = "BLOCKED"
        blocker["blocked_reason"] = "provenance not established"
        blocker["history"][-1]["status"] = "BLOCKED"
        dependent = copy.deepcopy(VALID_TRANSFERRED)
        dependent["depends_on"] = ["TR-9998"]
        errors = validate_register.check_register(
            register_with(blocker, dependent), load_schema(), REPO_ROOT
        )
        self.assertIn("while dependency TR-9998 is BLOCKED", "\n".join(errors))

    def test_rule13_self_dependency_rejected(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["depends_on"] = [entry["id"]]
        self.assert_rejected(entry, "depends on itself")

    def test_unknown_status_rejected_by_schema(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["status"] = "APPROVED"
        self.assert_rejected(entry, "is not one of")

    def test_unexpected_property_rejected_by_schema(self):
        entry = copy.deepcopy(VALID_TRANSFERRED)
        entry["looks_fine"] = True
        self.assert_rejected(entry, "unexpected property")


class SchemaValidatorTest(unittest.TestCase):
    """The schema subset validator must not silently ignore what it does not implement."""

    def test_unsupported_keyword_raises(self):
        with self.assertRaises(jsonschema_mini.SchemaError):
            jsonschema_mini.validate(1, {"type": "integer", "multipleOf": 2})

    def test_open_additional_properties_raises(self):
        with self.assertRaises(jsonschema_mini.SchemaError):
            jsonschema_mini.validate({}, {"type": "object", "additionalProperties": True})

    def test_booleans_are_not_integers(self):
        self.assertTrue(jsonschema_mini.validate(True, {"type": "integer"}))

    def test_register_schema_uses_only_the_supported_subset(self):
        """Guards against a schema change the validator would quietly stop enforcing."""
        jsonschema_mini.validate(load_register(), load_schema())


if __name__ == "__main__":
    unittest.main()
