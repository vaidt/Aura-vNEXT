"""The OIDC issuer must be the exact GitHub Actions issuer URL."""

import importlib.util
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / ".github/scripts"


class IssuerTests(unittest.TestCase):
    def test_exact_issuer_and_spoofed_urls(self):
        for filename in (
            "verify_m0_evidence_attestation.py",
            "verify_governance_acquisition_attestation.py",
        ):
            spec = importlib.util.spec_from_file_location(
                "verifier", SCRIPTS / filename
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            identity = "https://github.com/vaidt/Aura-vNEXT/.github/workflows/test.yml@refs/heads/test"

            def certificate(issuer):
                return {
                    "signature": {"certificate": {"issuer": issuer, "san": identity}},
                    "verifiedTimestamps": [1],
                }

            self.assertTrue(
                module.certificate_details(
                    certificate("https://token.actions.githubusercontent.com"), identity
                )["issuer_match"]
            )
            for issuer in (
                "https://evil.example/?issuer=token.actions.githubusercontent.com",
                "https://token.actions.githubusercontent.com.evil.example",
                "https://token.actions.githubusercontent.com@evil.example",
                "http://token.actions.githubusercontent.com",
                "token.actions.githubusercontent.com",
                "",
            ):
                with (
                    self.subTest(file=filename, issuer=issuer),
                    self.assertRaisesRegex(ValueError, "issuer"),
                ):
                    module.certificate_details(certificate(issuer), identity)
