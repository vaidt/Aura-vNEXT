"""Independent verification: the package verifies without the producer.

    PRODUCER -> Evidence Package -> fresh verifier environment -> VERIFIED
                mutated package  -> fresh verifier environment -> TAMPERED
                malformed package-> fresh verifier environment -> INVALID

The verifier runs as a separate process, in isolated mode, from a directory outside
the repository, holding only `core/` and `app/`, with the network disabled. The
producer, the fixture generator, and the test support are not present.

Scope of the claim: these runs establish independence **from the producer and from
this repository**, on one platform. They are not a cross-platform matrix and nothing
here should be read as one.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from _m0 import REPO_ROOT, refresh_manifest, read_records, write_records

sys.path.insert(0, str(REPO_ROOT / "tools"))
import independence_check  # noqa: E402


class IsolatedEnvironmentTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.env = independence_check.build_environment(self.root)

    def stage(self, name: str) -> Path:
        target = self.root / name
        shutil.copytree(independence_check.DEFAULT_PACKAGE, target)
        return target

    def test_environment_holds_only_the_verifier(self):
        """A verifier environment containing the producer would prove nothing."""
        self.assertEqual({"core", "app", "runner.py"},
                         {entry.name for entry in self.env.iterdir()})
        for forbidden in ("tools", "tests", "conformance", "evidence", "Makefile"):
            self.assertFalse((self.env / forbidden).exists(),
                             f"{forbidden} leaked into the verifier environment")

    def test_the_producer_is_absent_from_the_verifier_environment(self):
        """app/ carries both halves of the loop; only the verifier half may be copied.

        The claim under test is that a package verifies without the producer. An
        environment that happened to contain `app/producer/` could not distinguish a
        verifier that reads the package from one that reached back into producer-side
        code, so the exclusion is asserted rather than assumed.
        """
        self.assertTrue((self.env / "app" / "verifier").is_dir(),
                        "the verifier itself must be present")
        for application in independence_check.EXCLUDED_APPLICATIONS:
            with self.subTest(application=application):
                self.assertFalse(
                    (self.env / "app" / application).exists(),
                    f"app/{application}/ leaked into the verifier environment",
                )
        self.assertEqual(
            [], [path.name for path in (self.env / "app").iterdir()
                 if path.is_dir() and path.name != "verifier"],
            "an application other than the verifier is present in the environment",
        )

    def test_pristine_package_verifies_in_isolation(self):
        result = independence_check.run(self.env, self.stage("pristine"))
        self.assertEqual("VERIFIED", result["status"])
        self.assertEqual(3, result["entries"])

    def test_repository_is_not_importable_from_the_isolated_run(self):
        result = independence_check.run(self.env, self.stage("pristine"))
        self.assertFalse(result["_environment"]["repo_importable"],
                         f"sys.path was {result['_environment']['sys_path']}")

    def test_no_producer_side_module_is_loaded(self):
        result = independence_check.run(self.env, self.stage("pristine"))
        loaded = result["_environment"]["modules"]
        self.assertTrue(loaded)
        for module in loaded:
            self.assertIn(module.split(".")[0], ("core", "app"),
                          f"verification loaded {module}")

    def test_mutated_package_is_tampered_in_isolation(self):
        package = self.stage("mutated")
        records = read_records(package)
        records[1]["violations"][0]["confidence"] = 1
        write_records(package, records)
        refresh_manifest(package)
        self.assertEqual("TAMPERED", independence_check.run(self.env, package)["status"])

    def test_malformed_package_is_invalid_in_isolation(self):
        package = self.stage("malformed")
        (package / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual("INVALID", independence_check.run(self.env, package)["status"])

    def test_package_moved_outside_the_repository_still_verifies(self):
        """Verification must not depend on the package's location or its neighbours."""
        relocated = self.root / "somewhere" / "else" / "pkg"
        relocated.parent.mkdir(parents=True)
        shutil.copytree(independence_check.DEFAULT_PACKAGE, relocated)
        self.assertEqual("VERIFIED",
                         independence_check.run(self.env, relocated)["status"])

    def test_network_is_disabled_during_verification(self):
        """The runner replaces socket before importing the verifier.

        Proves the guard is armed: with the network disabled, verification still
        succeeds, so nothing in the path needed it.
        """
        runner = (self.env / "runner.py").read_text(encoding="utf-8")
        self.assertIn("socket.socket = _deny", runner)
        self.assertLess(runner.index("socket.socket = _deny"),
                        runner.index("from app.verifier import"),
                        "the network guard must be armed before the verifier is imported")
        self.assertEqual("VERIFIED",
                         independence_check.run(self.env, self.stage("pristine"))["status"])


class IndependenceCheckToolTest(unittest.TestCase):
    def test_the_recorded_check_passes_end_to_end(self):
        self.assertEqual(0, independence_check.main([]))


class VerifierCliTest(unittest.TestCase):
    """The CLI's exit status is the machine-readable result."""

    def test_exit_status_encodes_the_three_states(self):
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            pristine = root / "pristine"
            shutil.copytree(independence_check.DEFAULT_PACKAGE, pristine)

            tampered = root / "tampered"
            shutil.copytree(independence_check.DEFAULT_PACKAGE, tampered)
            records = read_records(tampered)
            records[0]["decision"] = "DENY"
            write_records(tampered, records)
            refresh_manifest(tampered)

            invalid = root / "invalid"
            shutil.copytree(independence_check.DEFAULT_PACKAGE, invalid)
            (invalid / "manifest.json").unlink()

            for package, expected_status, expected_code in (
                (pristine, "VERIFIED", 0),
                (tampered, "TAMPERED", 2),
                (invalid, "INVALID", 3),
            ):
                with self.subTest(expected=expected_status):
                    completed = subprocess.run(
                        [sys.executable, "-m", "app.verifier", str(package), "--json"],
                        cwd=REPO_ROOT, capture_output=True, text=True,
                    )
                    self.assertEqual(expected_code, completed.returncode)
                    self.assertEqual(expected_status,
                                     json.loads(completed.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
