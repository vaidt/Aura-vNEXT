"""Clean-room product test: the package is verified where the producer is not.

    ENVIRONMENT A   aura record -> Evidence Package
                        |
                        |  only the package is copied
                        v
    ENVIRONMENT B   fresh verifier -> VERIFIED

Environment B is built by `tools/independence_check.build_environment`: a directory
outside the repository holding `core/` and the verifier half of `app/` and nothing
else. The verifier runs there as a separate process in isolated mode, with the
environment cleared and `socket` disabled before it is imported.

`tests/test_independence.py` makes this claim for the committed reference package.
This suite makes it for a package produced by the product path, which is the claim
the product loop actually needs: evidence an application generated, verified without
that application.

Scope: CPython 3.11 on one platform. These runs establish independence from the
producer and from this repository. They are not a cross-platform matrix, and nothing
here should be read as one.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from _m0 import REPO_ROOT, read_records, refresh_manifest, write_records
from _product import produce_loan_package

sys.path.insert(0, str(REPO_ROOT / "tools"))
import independence_check  # noqa: E402


class CleanRoomProductTest(unittest.TestCase):
    def setUp(self):
        # Environment A: where the package is produced.
        self._producer_tmp = tempfile.TemporaryDirectory(prefix="aura-env-a-")
        self.addCleanup(self._producer_tmp.cleanup)
        self.environment_a = Path(self._producer_tmp.name)
        self.produced = produce_loan_package(self.environment_a)

        # Environment B: where it is verified. A separate temporary root, so nothing
        # from environment A is reachable by relative path.
        self._verifier_tmp = tempfile.TemporaryDirectory(prefix="aura-env-b-")
        self.addCleanup(self._verifier_tmp.cleanup)
        self.environment_b = Path(self._verifier_tmp.name)
        self.env = independence_check.build_environment(self.environment_b)

    def deliver(self, name: str = "delivered") -> Path:
        """Copy **only** the package into environment B."""
        target = self.environment_b / name
        shutil.copytree(self.produced, target)
        return target

    # ---- the clean-room claim ----------------------------------------------

    def test_a_produced_package_verifies_in_a_fresh_environment(self):
        result = independence_check.run(self.env, self.deliver())
        self.assertEqual("VERIFIED", result["status"])
        self.assertEqual(3, result["entries"])
        self.assertEqual("aura-evidence-loan-001", result["package_id"])

    def test_only_the_package_crosses_between_the_environments(self):
        """Nothing but the package files is delivered."""
        delivered = self.deliver()
        self.assertEqual(
            {"manifest.json", "evidence/audit.jsonl", "evidence/policy.json",
             "evidence/genesis.json"},
            {str(path.relative_to(delivered))
             for path in delivered.rglob("*") if path.is_file()},
        )

    def test_the_producer_is_not_present_in_the_verifying_environment(self):
        """The claim is that verification does not need the producer, so it is absent."""
        self.assertFalse((self.env / "app" / "producer").exists())
        self.assertFalse((self.env / "app" / "aura").exists())
        self.assertTrue((self.env / "app" / "verifier").is_dir())

    def test_no_producer_side_module_is_loaded_while_verifying(self):
        result = independence_check.run(self.env, self.deliver())
        loaded = result["_environment"]["modules"]
        self.assertTrue(loaded)
        for module in loaded:
            with self.subTest(module=module):
                self.assertNotIn(module.split(".")[0], ("tools", "tests"))
                self.assertFalse(module.startswith(("app.producer", "app.aura")),
                                 f"verification loaded {module}")

    def test_the_repository_is_not_importable_while_verifying(self):
        result = independence_check.run(self.env, self.deliver())
        self.assertFalse(result["_environment"]["repo_importable"],
                         f"sys.path was {result['_environment']['sys_path']}")

    def test_the_package_verifies_from_an_unrelated_location(self):
        """Verification depends on the package, not on where it happens to sit."""
        relocated = self.environment_b / "some" / "other" / "place" / "pkg"
        relocated.parent.mkdir(parents=True)
        shutil.copytree(self.produced, relocated)
        self.assertEqual("VERIFIED",
                         independence_check.run(self.env, relocated)["status"])

    # ---- the three states, all in the clean room ---------------------------

    def test_a_mutated_produced_package_is_tampered_in_the_clean_room(self):
        delivered = self.deliver("mutated")
        records = read_records(delivered)
        records[-1]["decision"] = "ALLOW"
        write_records(delivered, records)
        refresh_manifest(delivered)
        self.assertEqual("TAMPERED",
                         independence_check.run(self.env, delivered)["status"])

    def test_a_malformed_produced_package_is_invalid_in_the_clean_room(self):
        delivered = self.deliver("malformed")
        (delivered / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual("INVALID",
                         independence_check.run(self.env, delivered)["status"])

    def test_the_recorded_check_passes_against_a_produced_package(self):
        """The tool that prints the execution record runs on producer output too."""
        self.assertEqual(0, independence_check.main(["--package", str(self.produced)]))


class ProductLoopCheckToolTest(unittest.TestCase):
    """The end-to-end acceptance experiment, as the recorded tool runs it."""

    def test_the_product_loop_check_passes_end_to_end(self):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        import product_loop_check

        self.assertEqual(0, product_loop_check.main([]))


if __name__ == "__main__":
    unittest.main()
