"""Receipt output digests must bind the actual archived log bytes."""

import importlib.util
from pathlib import Path
import hashlib
import unittest

spec = importlib.util.spec_from_file_location(
    "m0_verifier",
    Path(__file__).resolve().parents[1]
    / ".github/scripts/verify_m0_evidence_attestation.py",
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class OutputBindingTests(unittest.TestCase):
    def test_exact_log_bytes_pass(self):
        raw = b"original output\n"
        verifier._verify_output_log(
            {
                "output_artifact": "test-output.log",
                "output_sha256": hashlib.sha256(raw).hexdigest(),
            },
            {"test-output.log": raw},
        )

    def test_changed_log_and_missing_digest_are_rejected(self):
        receipt = {
            "output_artifact": "test-output.log",
            "output_sha256": hashlib.sha256(b"original output\n").hexdigest(),
        }
        for digest in (receipt["output_sha256"], None, ""):
            with (
                self.subTest(digest=digest),
                self.assertRaisesRegex(ValueError, "output_sha256"),
            ):
                verifier._verify_output_log(
                    {**receipt, "output_sha256": digest},
                    {"test-output.log": b"changed output\n"},
                )

    def test_wrong_output_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "output_artifact"):
            verifier._verify_output_log(
                {"output_artifact": "another.log"}, {"test-output.log": b""}
            )
