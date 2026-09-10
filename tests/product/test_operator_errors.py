"""P6: the operator-facing interface, driven adversarially.

The verifier's classification is already pinned at the library level by
`tests/conformance/test_verifier_states.py` and `tests/product/test_producer_mutations.py`.
This suite asks a different question, and it is the one an operator cares about:

    when I make this mistake, or am handed a package in this state,
    what does the *command line* tell me, and what does it exit?

So every case here runs `aura verify` as a separate process and checks the verdict,
the exit status, and that the reason names the file at fault. A verifier that
classified correctly while the command line reported it as a crash, a bare stack
trace, or the wrong exit code would still be a broken product.

The invariant the whole matrix exists to protect is the three-state contract:

    INVALID   the package cannot be interpreted as an M0 Evidence Package
    TAMPERED  it is recognisable as one, and its protected evidence fails integrity

Collapsing these -- reporting a structural failure as tampering, or tampering as a
structural failure -- would destroy the only distinction the product sells.
"""

import json
import tempfile
import unittest
from pathlib import Path

from _m0 import read_records, refresh_manifest, write_records
from _product import run_aura, write_policy

VERIFIED, TAMPERED, INVALID = 0, 2, 3


class OperatorErrorTest(unittest.TestCase):
    """Every case listed in the productization error-handling review."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.policy = write_policy(self.root)
        self.package = self.root / "aura-evidence-loan-001"

        for index, (decision, request_id) in enumerate(
            [("ALLOW", "loan-001-intake"), ("REQUIRE_APPROVAL", "loan-001-assess"),
             ("DENY", "loan-001-settle")]
        ):
            completed = run_aura(
                "record", "--output", str(self.package), "--policy", str(self.policy),
                *(["--append"] if index else []),
                "--decision", decision, "--request-id", request_id,
                "--input-hash", "abcdef01" * 8,
                "--timestamp", f"2026-08-27T09:1{index}:00Z",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

        self.assertEqual(run_aura("verify", str(self.package)).returncode, VERIFIED,
                         "the fixture this suite mutates must start out VERIFIED")

    # ---- the assertion every case shares -------------------------------------

    def assertVerdict(self, expected: int, *, names: str | None = None):
        """Run `aura verify` and hold it to the whole operator-facing contract."""
        completed = run_aura("verify", str(self.package))
        label = {VERIFIED: "VERIFIED", TAMPERED: "TAMPERED", INVALID: "INVALID"}[expected]

        self.assertEqual(
            completed.returncode, expected,
            f"expected {label} (exit {expected}), got exit {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertIn(f"Result: {label}", completed.stdout)
        self.assertNotIn("Traceback", completed.stderr,
                         "an operator must never be shown a stack trace")
        if expected != VERIFIED:
            self.assertTrue(completed.stderr.strip(),
                            "a refusal must say why, on stderr")
            if names is not None:
                self.assertIn(names, completed.stderr,
                              "the reason must name the file at fault")
        return completed

    def manifest(self) -> dict:
        return json.loads((self.package / "manifest.json").read_text(encoding="utf-8"))

    def write_manifest(self, manifest: dict) -> None:
        (self.package / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    # ---- INVALID: the package cannot be interpreted --------------------------

    def test_missing_package(self):
        self.package = self.root / "was-never-here"
        self.assertVerdict(INVALID)

    def test_wrong_path_points_at_a_file(self):
        self.package = self.policy
        self.assertVerdict(INVALID, names="not a directory")

    def test_wrong_path_points_inside_the_package(self):
        self.package = self.package / "evidence"
        self.assertVerdict(INVALID)

    def test_missing_manifest(self):
        (self.package / "manifest.json").unlink()
        self.assertVerdict(INVALID, names="manifest.json")

    def test_malformed_json_in_the_manifest(self):
        (self.package / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertVerdict(INVALID, names="malformed JSON")

    def test_unsupported_profile(self):
        manifest = self.manifest()
        manifest["profile"] = "aura.evidence.package/99"
        self.write_manifest(manifest)
        self.assertVerdict(INVALID, names="unsupported profile")

    def test_malformed_evidence(self):
        (self.package / "evidence/audit.jsonl").write_text(
            "{ not a record\n", encoding="utf-8")
        self.assertVerdict(INVALID, names="evidence/audit.jsonl")

    def test_incomplete_package_missing_a_required_file(self):
        (self.package / "evidence/policy.json").unlink()
        self.assertVerdict(INVALID, names="evidence/policy.json")

    def test_incomplete_package_missing_the_chain_anchor(self):
        (self.package / "evidence/genesis.json").unlink()
        self.assertVerdict(INVALID, names="evidence/genesis.json")

    def test_an_empty_directory_is_not_a_package(self):
        self.package = self.root / "empty"
        self.package.mkdir()
        self.assertVerdict(INVALID)

    def test_a_record_outside_the_evidence_domain(self):
        """Not an audit entry at all, however well it is sealed."""
        records = read_records(self.package)
        records[-1]["decision"] = "PROBABLY"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertVerdict(INVALID)

    # ---- TAMPERED: recognisable evidence whose integrity fails ---------------

    def test_modified_evidence(self):
        records = read_records(self.package)
        records[-1]["decision"] = "ALLOW"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertVerdict(TAMPERED, names="evidence/audit.jsonl")

    def test_modified_policy(self):
        path = self.package / "evidence/policy.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        document["version"] = 99
        path.write_text(json.dumps(document, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
        refresh_manifest(self.package)
        self.assertVerdict(TAMPERED, names="policy_hash")

    def test_invalid_chain(self):
        records = read_records(self.package)
        records[1]["prev_hash"] = "0" * 64
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertVerdict(TAMPERED)

    def test_invalid_terminus(self):
        manifest = self.manifest()
        manifest["chain_head"] = "b" * 64
        self.write_manifest(manifest)
        self.assertVerdict(TAMPERED, names="chain_head")

    def test_invalid_manifest_commitment(self):
        manifest = self.manifest()
        manifest["files"]["evidence/policy.json"] = "0" * 64
        self.write_manifest(manifest)
        self.assertVerdict(TAMPERED, names="evidence/policy.json")

    def test_a_record_dropped_from_the_end(self):
        records = read_records(self.package)
        write_records(self.package, records[:-1])
        refresh_manifest(self.package)
        self.assertVerdict(TAMPERED)

    # ---- the contract the matrix protects ------------------------------------

    def test_the_three_states_are_never_collapsed(self):
        """One package, three states, three exit codes, in one run.

        Stated as a single test so that a change collapsing two of them cannot pass
        by having only one case updated.
        """
        self.assertEqual(run_aura("verify", str(self.package)).returncode, VERIFIED)

        records = read_records(self.package)
        records[-1]["decision"] = "ALLOW"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertEqual(run_aura("verify", str(self.package)).returncode, TAMPERED)

        (self.package / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual(run_aura("verify", str(self.package)).returncode, INVALID)

        self.assertEqual(len({VERIFIED, TAMPERED, INVALID}), 3)

    def test_no_operator_error_produces_a_stack_trace(self):
        """Whatever is done to a package, the operator gets a verdict, not a crash."""
        cases = {
            "no manifest": lambda: (self.package / "manifest.json").unlink(),
            "manifest is a directory": lambda: (
                (self.package / "manifest.json").unlink(),
                (self.package / "manifest.json").mkdir(),
            ),
            "audit is empty": lambda: (
                self.package / "evidence/audit.jsonl").write_text("", encoding="utf-8"),
            "audit is binary": lambda: (
                self.package / "evidence/audit.jsonl").write_bytes(b"\xff\xfe\x00\x01"),
            "policy is a list": lambda: (
                self.package / "evidence/policy.json").write_text("[]", encoding="utf-8"),
            "manifest files is a list": lambda: self.write_manifest(
                {**self.manifest(), "files": []}),
            "manifest declares an escaping path": lambda: self.write_manifest(
                {**self.manifest(),
                 "files": {**self.manifest()["files"], "../escape.json": "0" * 64}}),
        }
        for name, break_it in cases.items():
            with self.subTest(case=name):
                package = self.root / f"case-{abs(hash(name))}"
                run_aura("record", "--output", str(package), "--policy",
                         str(self.policy), "--decision", "DENY", "--request-id", "r",
                         "--input-hash", "abcdef01" * 8,
                         "--timestamp", "2026-08-27T09:10:00Z")
                original, self.package = self.package, package
                try:
                    break_it()
                    completed = run_aura("verify", str(self.package))
                    self.assertIn(completed.returncode, (TAMPERED, INVALID),
                                  f"{name}: exit {completed.returncode}\n"
                                  f"{completed.stdout}\n{completed.stderr}")
                    self.assertNotIn("Traceback", completed.stderr)
                    self.assertTrue(completed.stderr.strip())
                finally:
                    self.package = original


if __name__ == "__main__":
    unittest.main()
