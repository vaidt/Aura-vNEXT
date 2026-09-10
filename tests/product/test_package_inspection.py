"""`aura package`: the inspection step between producing a package and trusting one.

The product loop an operator walks is CREATE -> INSPECT -> COPY -> VERIFY. This
suite covers INSPECT. Its obligations are narrow and worth stating plainly:

  * it must tell an operator which file is the evidence, which is the policy, and
    which is the chain anchor, without their having to read the contract;
  * it must show which files the manifest actually commits to, so a file that
    travelled along with a package cannot be mistaken for evidence;
  * it must never return a verdict. Describing a package is not verifying one, and
    the verdict exit statuses belong to `aura verify` alone.

The last of these is the one that would be dangerous to lose: an operator who read
a description and saw exit status 0 must not conclude that anything was checked.
"""

import json
import tempfile
import unittest
from pathlib import Path

from _m0 import read_records, refresh_manifest, write_records
from _product import run_aura, write_policy

VERDICT_STATUSES = (2, 3)   # TAMPERED, INVALID -- reserved for `aura verify`


class PackageInspectionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.policy = write_policy(self.root)
        self.package = self.root / "aura-evidence-loan-001"
        completed = run_aura(
            "record", "--output", str(self.package), "--policy", str(self.policy),
            "--decision", "DENY", "--request-id", "loan-001-settle",
            "--input-hash", "a" * 64, "--timestamp", "2026-08-27T09:16:31Z",
            "--violation", "LOAN.DTI_EXCEEDED:BLOCK:1.0",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def inspect(self, *extra: str):
        return run_aura("package", str(self.package), *extra)

    # ---- what an operator must be able to learn ------------------------------

    def test_names_the_role_of_every_required_file(self):
        stdout = self.inspect().stdout
        for path in ("evidence/audit.jsonl", "evidence/policy.json",
                     "evidence/genesis.json", "manifest.json"):
            self.assertIn(path, stdout)
        for role in ("THE EVIDENCE", "THE POLICY", "THE ANCHOR", "THE COMMITMENT"):
            self.assertIn(role, stdout)

    def test_reports_the_package_identity_and_chain_terminus(self):
        described = json.loads(self.inspect("--json").stdout)
        manifest = json.loads((self.package / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(described["package_id"], manifest["package_id"])
        self.assertEqual(described["profile"], manifest["profile"])
        self.assertEqual(described["entry_count"], manifest["entry_count"])
        self.assertEqual(described["chain_head"], manifest["chain_head"])

    def test_lists_the_decisions_the_package_records(self):
        stdout = self.inspect().stdout
        self.assertIn("loan-001-settle", stdout)
        self.assertIn("DENY", stdout)
        self.assertIn("1 violation(s)", stdout)

    def test_points_the_operator_at_the_command_that_does_judge(self):
        stdout = self.inspect().stdout
        self.assertIn("not a verdict", stdout)
        self.assertIn("aura verify", stdout)

    # ---- what the manifest covers, and what it does not ----------------------

    def test_marks_a_file_the_manifest_does_not_declare(self):
        (self.package / "notes.txt").write_text("hand-added\n", encoding="utf-8")
        described = json.loads(self.inspect("--json").stdout)
        entry = next(e for e in described["files"] if e["path"] == "notes.txt")
        self.assertFalse(entry["declared"])
        self.assertIn("not evidence", self.inspect().stdout)

    def test_marks_a_declared_file_that_is_absent(self):
        (self.package / "evidence/policy.json").unlink()
        described = json.loads(self.inspect("--json").stdout)
        entry = next(e for e in described["files"]
                     if e["path"] == "evidence/policy.json")
        self.assertTrue(entry["declared"])
        self.assertFalse(entry["present"])
        self.assertIn("(MISSING)", self.inspect().stdout)

    # ---- inspection is not verification --------------------------------------

    def test_never_returns_a_verdict_status_for_an_intact_package(self):
        self.assertNotIn(self.inspect().returncode, VERDICT_STATUSES)

    def test_never_returns_a_verdict_status_for_a_tampered_package(self):
        """A package `verify` calls TAMPERED is still merely described here."""
        records = read_records(self.package)
        records[-1]["decision"] = "ALLOW"
        write_records(self.package, records)
        refresh_manifest(self.package)

        self.assertEqual(run_aura("verify", str(self.package)).returncode, 2)
        self.assertNotIn(self.inspect().returncode, VERDICT_STATUSES)

    def test_never_returns_a_verdict_status_for_an_unreadable_package(self):
        (self.package / "manifest.json").write_text("{ not json", encoding="utf-8")
        completed = self.inspect()
        self.assertNotIn(completed.returncode, VERDICT_STATUSES)
        self.assertEqual(completed.returncode, 65)
        self.assertIn("malformed JSON", completed.stderr)

    def test_a_path_that_is_not_a_directory_is_refused(self):
        completed = run_aura("package", str(self.policy))
        self.assertEqual(completed.returncode, 65)
        self.assertIn("not a directory", completed.stderr)

    def test_inspection_does_not_modify_the_package(self):
        before = {p.relative_to(self.package).as_posix(): p.read_bytes()
                  for p in sorted(self.package.rglob("*")) if p.is_file()}
        self.inspect()
        after = {p.relative_to(self.package).as_posix(): p.read_bytes()
                 for p in sorted(self.package.rglob("*")) if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(run_aura("verify", str(self.package)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
