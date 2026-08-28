"""The three-state verifier contract.

VERIFIED, TAMPERED, and INVALID are distinct external results and are never collapsed:

    VERIFIED  structurally valid, and every required integrity check succeeded
    TAMPERED  recognisable as an M0 package, but protected evidence fails integrity
    INVALID   cannot be interpreted as an M0 Evidence Package at all

The distinction is not cosmetic. INVALID says "I cannot read this"; TAMPERED says
"I read this, and it has been altered". Only the second is a statement about evidence.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _m0 import (REFERENCE_PACKAGE, copy_reference_package, read_records,
                 refresh_manifest, write_records)

from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package


class VerifierStateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.package = copy_reference_package(self.tmp)

    def status(self) -> str:
        return verify_package(self.package).status

    def assertStatus(self, expected: str, note: str):
        result = verify_package(self.package)
        self.assertEqual(
            expected, result.status,
            f"{note}: expected {expected}, got {result.status} ({result.reasons})",
        )
        return result

    # ---- VERIFIED -----------------------------------------------------------

    def test_reference_package_is_verified(self):
        result = self.assertStatus(VERIFIED, "reference package")
        self.assertEqual((), result.reasons)
        self.assertEqual("aura-evidence-loan-001", result.package_id)
        self.assertEqual(3, result.entries)

    def test_verified_matches_the_packages_own_expected_result(self):
        """The package states what it should verify as; the verifier must agree."""
        expected = json.loads(
            (self.package / "expected/result.json").read_text(encoding="utf-8")
        )
        result = verify_package(self.package).as_dict()
        self.assertEqual(expected["status"], result["status"])
        self.assertEqual(expected["package_id"], result["package_id"])
        self.assertEqual(expected["entries"], result["entries"])
        self.assertEqual(expected["reasons"], result["reasons"])

    # ---- TAMPERED -----------------------------------------------------------

    def test_altered_protected_field_is_tampered(self):
        records = read_records(self.package)
        records[0]["decision"] = "DENY"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertStatus(TAMPERED, "altered decision")

    def test_stale_manifest_digest_is_tampered(self):
        records = read_records(self.package)
        records[0]["request_id"] = "other"
        write_records(self.package, records)
        self.assertStatus(TAMPERED, "stale manifest digest")

    def test_broken_chain_link_is_tampered(self):
        records = read_records(self.package)
        records[1]["prev_hash"] = "0" * 64
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertStatus(TAMPERED, "broken link")

    def test_policy_swapped_for_a_different_document_is_tampered(self):
        (self.package / "evidence/policy.json").write_text(
            json.dumps({"policy_id": "other", "version": 1, "rules": []},
                       sort_keys=True, indent=2) + "\n", encoding="utf-8")
        refresh_manifest(self.package)
        self.assertStatus(TAMPERED, "policy swapped")

    def test_tampered_is_reported_with_reasons(self):
        records = read_records(self.package)
        records[2]["decision"] = "ALLOW"
        write_records(self.package, records)
        refresh_manifest(self.package)
        result = self.assertStatus(TAMPERED, "reasons")
        self.assertTrue(any("entry_hash" in r for r in result.reasons), result.reasons)

    # ---- INVALID ------------------------------------------------------------

    def test_missing_manifest_is_invalid(self):
        (self.package / "manifest.json").unlink()
        self.assertStatus(INVALID, "missing manifest")

    def test_malformed_manifest_json_is_invalid(self):
        (self.package / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertStatus(INVALID, "malformed manifest")

    def test_malformed_audit_json_is_invalid(self):
        (self.package / "evidence/audit.jsonl").write_text(
            "{\"schema\": broken}\n", encoding="utf-8")
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "malformed audit record")

    def test_malformed_policy_json_is_invalid(self):
        (self.package / "evidence/policy.json").write_text("[[[", encoding="utf-8")
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "malformed policy")

    def test_unsupported_profile_is_invalid(self):
        path = self.package / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["profile"] = "aura.evidence.package/99"
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
        self.assertStatus(INVALID, "unsupported profile")

    def test_unsupported_audit_schema_is_invalid(self):
        records = read_records(self.package)
        for record in records:
            record["schema"] = "aura.audit/99"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "unsupported schema")

    def test_missing_required_file_is_invalid(self):
        (self.package / "evidence/genesis.json").unlink()
        self.assertStatus(INVALID, "missing required file")

    def test_file_not_declared_in_the_manifest_is_invalid(self):
        path = self.package / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        del manifest["files"]["evidence/policy.json"]
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
        self.assertStatus(INVALID, "undeclared required file")

    def test_empty_audit_chain_is_invalid(self):
        (self.package / "evidence/audit.jsonl").write_text("", encoding="utf-8")
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "empty chain")

    def test_record_without_an_entry_hash_is_invalid(self):
        records = read_records(self.package)
        del records[0]["entry_hash"]
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "record carries no entry_hash")

    def test_record_with_an_uncanonicalisable_member_is_invalid(self):
        """A float cannot exist in AURA-CANON/1, so the record cannot be read at all."""
        records = read_records(self.package)
        records[1]["violations"][0]["confidence"] = 0.95
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "float in a protected member")

    def test_null_member_is_invalid(self):
        records = read_records(self.package)
        records[0]["metadata"]["actor"] = None
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "null in a protected member")

    def test_missing_package_directory_is_invalid(self):
        self.assertEqual(INVALID, verify_package(self.tmp / "does-not-exist").status)

    def test_empty_directory_is_invalid(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        self.assertEqual(INVALID, verify_package(empty).status)

    def test_genesis_anchor_missing_is_invalid(self):
        path = self.package / "evidence/genesis.json"
        path.write_text(json.dumps({"package_id": "x"}, indent=2) + "\n", encoding="utf-8")
        refresh_manifest(self.package)
        self.assertStatus(INVALID, "genesis without prev_hash")


class StateSeparationTest(unittest.TestCase):
    """The three states must stay three states."""

    def test_the_three_states_are_distinct_values(self):
        self.assertEqual(3, len({VERIFIED, TAMPERED, INVALID}))

    def test_the_verifier_returns_nothing_outside_the_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            package = copy_reference_package(root)
            observed = {verify_package(package).status}

            broken = root / "broken"
            shutil.copytree(REFERENCE_PACKAGE, broken)
            (broken / "manifest.json").write_text("{", encoding="utf-8")
            observed.add(verify_package(broken).status)

            altered = root / "altered"
            shutil.copytree(REFERENCE_PACKAGE, altered)
            records = read_records(altered)
            records[0]["decision"] = "DENY"
            write_records(altered, records)
            refresh_manifest(altered)
            observed.add(verify_package(altered).status)

            self.assertEqual({VERIFIED, TAMPERED, INVALID}, observed)


if __name__ == "__main__":
    unittest.main()
