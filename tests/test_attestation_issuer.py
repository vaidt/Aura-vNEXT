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
                    "signature": {"certificate": {"issuer": issuer, "subjectAlternativeName": identity}},
                    "verifiedTimestamps": [1],
                }

            self.assertTrue(
                module.certificate_details(
                    certificate("https://token.actions.githubusercontent.com"), identity
                )["issuer_match"]
            )
            for wrong in ("https://evil.example", None):
                forged = certificate(wrong)
                forged["signature"]["certificate"]["unrelated"] = (
                    "https://token.actions.githubusercontent.com"
                )
                with (
                    self.subTest(file=filename, issuer=wrong),
                    self.assertRaisesRegex(ValueError, "issuer"),
                ):
                    module.certificate_details(forged, identity)
            missing = certificate("https://token.actions.githubusercontent.com")
            del missing["signature"]["certificate"]["issuer"]
            missing["signature"]["certificate"]["unrelated"] = (
                "https://token.actions.githubusercontent.com"
            )
            with self.assertRaisesRegex(ValueError, "issuer"):
                module.certificate_details(missing, identity)
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


    def test_exact_subject_alternative_name_in_both_verifiers(self):
        expected = (
            "https://github.com/vaidt/Aura-vNEXT/"
            ".github/workflows/test.yml@refs/heads/test"
        )
        wrong_values = (
            expected + ".attacker.example",
            expected + "/extra",
            "https://evil.example/?identity=" + expected,
            "prefix-" + expected,
            expected.replace("@refs/heads/test", "@refs/heads/test-more"),
            expected.replace("vaidt/Aura-vNEXT", "vaidt/Aura-vNEXT-other"),
            expected + " ",
            "",
            None,
            [expected],
            {"uri": expected},
        )
        for filename in (
            "verify_m0_evidence_attestation.py",
            "verify_governance_acquisition_attestation.py",
        ):
            spec = importlib.util.spec_from_file_location(
                "verifier_exact_san", SCRIPTS / filename
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            def verified(san, *, include_san=True):
                cert = {
                    "issuer": "https://token.actions.githubusercontent.com",
                    "san": expected,
                    "buildSignerURI": expected,
                    "unrelated": expected,
                }
                if include_san:
                    cert["subjectAlternativeName"] = san
                return {
                    "signature": {"certificate": cert},
                    "verifiedTimestamps": [1],
                }

            with self.subTest(file=filename, case="valid"):
                result = module.certificate_details(verified(expected), expected)
                self.assertEqual(result["certificate_identity"], expected)

            for candidate in wrong_values:
                with (
                    self.subTest(file=filename, candidate=repr(candidate)),
                    self.assertRaisesRegex(ValueError, "SAN"),
                ):
                    module.certificate_details(verified(candidate), expected)

            with (
                self.subTest(file=filename, case="absent-with-decoys"),
                self.assertRaisesRegex(ValueError, "SAN"),
            ):
                module.certificate_details(verified(None, include_san=False), expected)

            with (
                self.subTest(file=filename, case="no-verified-timestamp"),
                self.assertRaisesRegex(ValueError, "timestamp"),
            ):
                item = verified(expected)
                item["verifiedTimestamps"] = []
                module.certificate_details(item, expected)
