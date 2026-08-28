"""The published `aura` command-line contract, pinned as an executable statement.

Everything asserted here is published to operators. An operator is invited to
branch on the exit status alone, so the status is part of the product surface and
not an implementation detail: these tests exist so it cannot drift.

    0   VERIFIED, or a command that succeeded
    2   TAMPERED
    3   INVALID
    64  the command line could not be understood
    65  the command was understood, and the event could not be recorded

The distinction that matters most is 64 against 2. argparse exits 2 by default,
which is the verdict TAMPERED. A caller reading only the status would then read a
mistyped flag as a failed integrity check.
"""

import tempfile
import unittest
from pathlib import Path

from _product import run_aura, write_policy

VERIFIED, TAMPERED, INVALID = 0, 2, 3
USAGE, REFUSED = 64, 65


class ExitStatusContractTest(unittest.TestCase):
    """The five exit statuses, each reached by the route the documentation names."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.policy = write_policy(self.root)

    def record_one(self, output: Path, *extra: str):
        return run_aura(
            "record", "--output", str(output), "--policy", str(self.policy),
            "--decision", "DENY", "--request-id", "r-1", "--input-hash", "a" * 64,
            "--timestamp", "2026-08-27T09:15:00Z", *extra,
        )

    # ---- 0 and 3: the verdict statuses reachable without tampering -----------

    def test_verify_of_a_produced_package_is_zero(self):
        package = self.root / "pkg"
        self.assertEqual(self.record_one(package).returncode, 0)
        self.assertEqual(run_aura("verify", str(package)).returncode, VERIFIED)

    def test_verify_of_a_missing_path_is_invalid_not_a_crash(self):
        completed = run_aura("verify", str(self.root / "absent"))
        self.assertEqual(completed.returncode, INVALID)
        self.assertIn("INVALID", completed.stdout)

    def test_verify_of_a_file_rather_than_a_directory_is_invalid(self):
        completed = run_aura("verify", str(self.policy))
        self.assertEqual(completed.returncode, INVALID)

    # ---- 64: the command line itself ----------------------------------------
    #
    # Each of these must be distinguishable from TAMPERED by exit status alone.

    def test_no_command_is_a_usage_error(self):
        self.assertEqual(run_aura().returncode, USAGE)

    def test_unknown_command_is_a_usage_error(self):
        self.assertEqual(run_aura("frobnicate").returncode, USAGE)

    def test_missing_required_argument_is_a_usage_error(self):
        self.assertEqual(run_aura("verify").returncode, USAGE)

    def test_unknown_option_is_a_usage_error(self):
        self.assertEqual(run_aura("verify", "--typo", str(self.root)).returncode, USAGE)

    def test_value_outside_a_declared_choice_is_a_usage_error(self):
        completed = self.record_one(self.root / "pkg", "--decision", "MAYBE")
        self.assertEqual(completed.returncode, USAGE)

    def test_a_usage_error_never_returns_the_tampered_status(self):
        """The collision this contract exists to prevent, stated directly."""
        for argv in ([], ["frobnicate"], ["verify"], ["record"],
                     ["verify", "--typo", str(self.root)]):
            with self.subTest(argv=argv):
                self.assertNotEqual(run_aura(*argv).returncode, TAMPERED)

    def test_help_succeeds_for_every_command(self):
        for argv in (["--help"], ["record", "--help"], ["verify", "--help"]):
            with self.subTest(argv=argv):
                completed = run_aura(*argv)
                self.assertEqual(completed.returncode, 0)
                self.assertIn("usage:", completed.stdout)

    # ---- 65: understood, and refused ----------------------------------------

    def test_missing_policy_file_is_refused(self):
        completed = self.record_one(self.root / "pkg",
                                    "--policy", str(self.root / "absent.json"))
        self.assertEqual(completed.returncode, REFUSED)
        self.assertIn("cannot be read", completed.stderr)

    def test_malformed_policy_file_is_refused(self):
        broken = self.root / "broken.json"
        broken.write_text("{ not json", encoding="utf-8")
        completed = self.record_one(self.root / "pkg", "--policy", str(broken))
        self.assertEqual(completed.returncode, REFUSED)
        self.assertIn("malformed JSON", completed.stderr)

    def test_input_reference_is_required(self):
        completed = run_aura(
            "record", "--output", str(self.root / "pkg"), "--policy", str(self.policy),
            "--decision", "DENY", "--request-id", "r-1",
        )
        self.assertEqual(completed.returncode, REFUSED)

    def test_recording_over_an_existing_package_is_refused(self):
        package = self.root / "pkg"
        self.assertEqual(self.record_one(package).returncode, 0)
        completed = self.record_one(package)
        self.assertEqual(completed.returncode, REFUSED)
        self.assertIn("--append", completed.stderr)

    def test_appending_to_a_package_that_does_not_exist_is_refused(self):
        completed = self.record_one(self.root / "absent", "--append")
        self.assertEqual(completed.returncode, REFUSED)

    def test_a_refusal_never_returns_a_verdict_status(self):
        """A producer refusal is not a verdict about a package."""
        completed = self.record_one(self.root / "pkg", "--input-hash", "not-a-digest")
        self.assertEqual(completed.returncode, REFUSED)
        self.assertNotIn(completed.returncode, (VERIFIED, TAMPERED, INVALID))


class StreamContractTest(unittest.TestCase):
    """Which stream carries what: the verdict on stdout, the reasons on stderr."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.policy = write_policy(self.root)
        self.package = self.root / "pkg"
        run_aura("record", "--output", str(self.package), "--policy", str(self.policy),
                 "--decision", "DENY", "--request-id", "r-1", "--input-hash", "a" * 64,
                 "--timestamp", "2026-08-27T09:15:00Z")

    def test_the_verdict_is_on_stdout(self):
        completed = run_aura("verify", str(self.package))
        self.assertIn("Result: VERIFIED", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_the_reason_for_a_refusal_is_on_stderr(self):
        completed = run_aura("verify", str(self.root / "absent"))
        self.assertIn("Result: INVALID", completed.stdout)
        self.assertTrue(completed.stderr.strip(),
                        "an INVALID verdict must say why, on stderr")

    def test_json_output_is_parseable_on_stdout_alone(self):
        import json

        completed = run_aura("verify", str(self.package), "--json")
        document = json.loads(completed.stdout)
        self.assertEqual(document["status"], "VERIFIED")
        self.assertEqual(document["entries"], 1)


if __name__ == "__main__":
    unittest.main()
