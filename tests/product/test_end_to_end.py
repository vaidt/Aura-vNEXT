"""The acceptance experiment, driven through the `aura` command line.

    APPLICATION EVENT -> aura record -> package -> aura verify -> VERIFIED
                         mutate the decision       -> aura verify -> TAMPERED
                         malform the package       -> aura verify -> INVALID

Every step runs the command line as a separate process, so what is under test is the
product surface an operator actually has, not a function call arranged to succeed.
The package is produced here rather than copied from `evidence/examples/`: a suite
that mutated the committed fixture would be testing the fixture.
"""

import json
import tempfile
import unittest
from pathlib import Path

from _m0 import read_records, refresh_manifest, write_records
from _product import LOAN_POLICY, run_aura, write_policy

PACKAGE_ID = "aura-evidence-loan-001"


class EndToEndProductLoopTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.policy = write_policy(self.root)
        self.package = self.root / PACKAGE_ID

    # ---- EVENT -> PRODUCER -> PACKAGE ---------------------------------------

    def record_intake(self, *extra: str):
        return run_aura(
            "record", "--output", str(self.package), "--policy", str(self.policy),
            "--decision", "ALLOW", "--request-id", "loan-001-intake",
            "--input-hash", "b" * 64, "--timestamp", "2026-08-27T09:15:00Z",
            "--metadata", "actor=agent-17", "--metadata", "stage=intake", *extra,
        )

    def record_assess(self):
        return run_aura(
            "record", "--append", "--output", str(self.package),
            "--policy", str(self.policy), "--decision", "REQUIRE_APPROVAL",
            "--request-id", "loan-001-assess", "--input-hash", "c" * 64,
            "--timestamp", "2026-08-27T09:15:04Z", "--shadow-hash", "a" * 64,
            "--violation", "LOAN.DTI_EXCEEDED:BLOCK:0.95",
            "--violation", "LOAN.MANUAL_REVIEW:FLAG:0.5",
            "--metadata", "actor=agent-17", "--metadata", "stage=assess",
        )

    def record_settle(self):
        return run_aura(
            "record", "--append", "--output", str(self.package),
            "--policy", str(self.policy), "--decision", "DENY",
            "--request-id", "loan-001-settle", "--input-hash", "a" * 64,
            "--timestamp", "2026-08-27T09:16:31Z",
            "--violation", "LOAN.DTI_EXCEEDED:BLOCK:1.0",
            "--metadata", "actor=reviewer-3", "--metadata", "stage=settle",
        )

    def build_the_package(self) -> Path:
        """Three application decisions, recorded by three separate invocations."""
        for step, record in enumerate(
            (self.record_intake, self.record_assess, self.record_settle)
        ):
            completed = record()
            self.assertEqual(0, completed.returncode,
                             f"step {step}: {completed.stderr}")
        return self.package

    def verify(self, package: Path):
        return run_aura("verify", str(package))

    def records(self):
        return read_records(self.package)

    # ---- the experiment -----------------------------------------------------

    def test_recorded_package_verifies(self):
        """EVENT -> aura record -> aura-evidence-loan-001 -> VERIFIED."""
        package = self.build_the_package()

        completed = self.verify(package)
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("AURA EVIDENCE VERIFIER", completed.stdout)
        self.assertIn("Result: VERIFIED", completed.stdout)
        self.assertIn(f"Package: {PACKAGE_ID}", completed.stdout)

    def test_the_recorded_chain_is_what_the_application_stated(self):
        self.build_the_package()
        records = self.records()
        self.assertEqual(
            ["loan-001-intake", "loan-001-assess", "loan-001-settle"],
            [r["request_id"] for r in records],
        )
        self.assertEqual(["ALLOW", "REQUIRE_APPROVAL", "DENY"],
                         [r["decision"] for r in records])
        self.assertEqual([0, 1, 2], [r["seq"] for r in records])
        # Confidence reached the evidence as exact basis points, not a float.
        self.assertEqual([9500, 5000],
                         [v["confidence"] for v in records[1]["violations"]])
        self.assertEqual("a" * 64, records[1]["shadow_hash"])
        self.assertNotIn("shadow_hash", records[0])

    def test_mutating_the_decision_yields_tampered(self):
        """DENY -> ALLOW -> aura verify -> TAMPERED.

        The manifest digests are repaired afterwards, so the mutation has to defeat
        the canonical binding rather than being caught by the outer checksum.
        """
        package = self.build_the_package()
        self.assertEqual(0, self.verify(package).returncode)

        records = self.records()
        self.assertEqual("DENY", records[-1]["decision"])
        records[-1]["decision"] = "ALLOW"
        write_records(package, records)
        refresh_manifest(package)

        completed = self.verify(package)
        self.assertEqual(2, completed.returncode)
        self.assertIn("Result: TAMPERED", completed.stdout)
        self.assertTrue(completed.stderr.strip(), "TAMPERED with no stated reason")

    def test_malforming_the_package_yields_invalid(self):
        """A package that cannot be read at all -> INVALID, never TAMPERED."""
        package = self.build_the_package()
        (package / "manifest.json").write_text("{ not json", encoding="utf-8")

        completed = self.verify(package)
        self.assertEqual(3, completed.returncode)
        self.assertIn("Result: INVALID", completed.stdout)

    def test_the_three_states_are_distinct_exit_statuses(self):
        """The verdict is machine-readable without parsing any output."""
        self.build_the_package()
        self.assertEqual(0, self.verify(self.package).returncode)

        records = self.records()
        records[0]["input_hash"] = "d" * 64
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertEqual(2, self.verify(self.package).returncode)

        (self.package / "evidence/audit.jsonl").write_text("not jsonl\n",
                                                           encoding="utf-8")
        refresh_manifest(self.package)
        self.assertEqual(3, self.verify(self.package).returncode)

    # ---- the surface itself -------------------------------------------------

    def test_record_reports_the_chain_it_committed_to(self):
        completed = self.record_intake()
        self.assertIn("AURA EVIDENCE PRODUCER", completed.stdout)
        manifest = json.loads((self.package / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn(manifest["chain_head"], completed.stdout)

    def test_record_emits_machine_readable_output(self):
        completed = self.record_intake("--json")
        self.assertEqual(0, completed.returncode, completed.stderr)
        reported = json.loads(completed.stdout)
        self.assertEqual(PACKAGE_ID, reported["package_id"])
        self.assertEqual(1, reported["entries"])
        self.assertEqual(self.records()[0]["entry_hash"], reported["chain_head"])

    def test_verify_emits_machine_readable_output(self):
        self.build_the_package()
        completed = run_aura("verify", str(self.package), "--json")
        reported = json.loads(completed.stdout)
        self.assertEqual("VERIFIED", reported["status"])
        self.assertEqual(3, reported["entries"])
        self.assertEqual([], reported["reasons"])

    def test_the_package_id_defaults_to_the_output_directory(self):
        self.record_intake()
        manifest = json.loads((self.package / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(PACKAGE_ID, manifest["package_id"])

    def test_recording_over_an_existing_package_is_refused(self):
        """Overwriting in place would discard evidence already recorded."""
        self.assertEqual(0, self.record_intake().returncode)
        completed = self.record_intake()
        self.assertEqual(65, completed.returncode)
        self.assertIn("--append", completed.stderr)
        # The existing package is untouched and still verifies.
        self.assertEqual(0, self.verify(self.package).returncode)

    def test_appending_to_a_package_that_does_not_exist_is_refused(self):
        completed = self.record_assess()
        self.assertEqual(65, completed.returncode)
        self.assertFalse(self.package.exists())

    def test_an_undefined_decision_is_refused_by_the_command_line(self):
        completed = run_aura(
            "record", "--output", str(self.package), "--policy", str(self.policy),
            "--decision", "WHATEVER", "--request-id", "r", "--input-hash", "b" * 64,
        )
        self.assertNotEqual(0, completed.returncode)
        self.assertFalse(self.package.exists())

    def test_a_refused_event_writes_nothing(self):
        """A producer that emitted a package it could not verify would be worse than one
        that refuses."""
        completed = run_aura(
            "record", "--output", str(self.package), "--policy", str(self.policy),
            "--decision", "DENY", "--request-id", "r", "--input-hash", "not-a-digest",
        )
        self.assertEqual(65, completed.returncode)
        self.assertFalse(self.package.exists())

    def test_the_input_reference_can_be_derived_from_a_local_input(self):
        import hashlib

        payload = self.root / "application-input.json"
        payload.write_bytes(b'{"applicant":"A-1","dti_bp":4700}')
        completed = run_aura(
            "record", "--output", str(self.package), "--policy", str(self.policy),
            "--decision", "DENY", "--request-id", "loan-001",
            "--input-file", str(payload), "--timestamp", "2026-08-27T09:15:00Z",
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(hashlib.sha256(payload.read_bytes()).hexdigest(),
                         self.records()[0]["input_hash"])
        self.assertEqual(0, self.verify(self.package).returncode)

    def test_the_policy_label_defaults_to_the_policy_document(self):
        self.record_intake()
        self.assertEqual("loan.underwriting/2", self.records()[0]["policy_repr"])

    def test_a_batch_of_events_can_be_recorded_from_a_file(self):
        events = self.root / "events.json"
        events.write_text(json.dumps([
            {"request_id": "e-0", "timestamp": "2026-08-27T09:15:00Z",
             "decision": "ALLOW", "input_hash": "b" * 64},
            {"request_id": "e-1", "timestamp": "2026-08-27T09:15:01Z",
             "decision": "DENY", "input_hash": "c" * 64,
             "violations": [{"rule": "R.A", "action": "BLOCK", "confidence": "0.95"}]},
        ]), encoding="utf-8")

        completed = run_aura("record", "--output", str(self.package),
                             "--policy", str(self.policy), "--events", str(events))
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertEqual(0, self.verify(self.package).returncode)
        self.assertEqual(["e-0", "e-1"], [r["request_id"] for r in self.records()])

    def test_the_policy_document_is_carried_into_the_package(self):
        self.record_intake()
        self.assertEqual(
            LOAN_POLICY,
            json.loads((self.package / "evidence/policy.json").read_text(encoding="utf-8")),
        )


if __name__ == "__main__":
    unittest.main()
