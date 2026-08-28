"""Regression suite for PR #1 review findings P0-R1 .. P0-R5.

Each finding was reproduced against commit a9fa832 before the fix; the reproduction
is recorded in the test that closes it. The classification rule is preserved
throughout: INVALID means the record or package cannot be accepted as a valid M0
structure or a supported verification contract; TAMPERED means a structurally valid
M0 object failed an integrity check.
"""

import json
import tempfile
import unittest
from pathlib import Path

from _m0 import (copy_reference_package, read_records, refresh_manifest, reseal_chain,
                 write_records)

from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package
from core.canonical import CanonicalisationError, canonical_bytes
from core.models import SchemaError, validate_audit_record


def seal_records_only(package: Path) -> None:
    """Recompute each record's entry_hash over its own members, without relinking.

    ``reseal_chain`` rewrites prev_hash as well, which would silently restore a
    dropped or altered prev_hash and make the test pass for the wrong reason. This
    keeps the chain wiring exactly as the test left it.

    A record that cannot be canonicalised at all keeps whatever digest it carries:
    there is no preimage to hash, and the verifier must classify it INVALID on
    structure alone.
    """
    import hashlib

    records = read_records(package)
    for record in records:
        protected = {k: v for k, v in record.items() if k != "entry_hash"}
        try:
            record["entry_hash"] = hashlib.sha256(
                canonical_bytes(protected)
            ).hexdigest()
        except CanonicalisationError:
            pass
    write_records(package, records)
    refresh_manifest(package)


class _PackageCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.package = copy_reference_package(self.tmp)

    def assertStatus(self, expected: str, note: str):
        result = verify_package(self.package)
        self.assertEqual(
            expected, result.status,
            f"{note}: expected {expected}, got {result.status} ({result.reasons})",
        )
        return result

    def mutate_and_reseal(self, index: int, mutate):
        """Apply a change, then reseal so the digests are internally consistent.

        Resealing is what makes these tests meaningful: without it the record would
        fail its digest and report TAMPERED, and the structural gap under test would
        stay hidden. Before the fix, each of these reached VERIFIED.
        """
        records = read_records(self.package)
        mutate(records[index])
        write_records(self.package, records)
        reseal_chain(self.package)


class P0R1ExactAuditSchemaTest(_PackageCase):
    """A record is an AuditEntry only if it carries the M0 field set, correctly typed."""

    def test_control_reference_package_still_verifies(self):
        self.assertStatus(VERIFIED, "unmodified reference package")

    def test_missing_required_field_is_invalid(self):
        self.mutate_and_reseal(0, lambda r: r.pop("policy_repr"))
        result = self.assertStatus(INVALID, "missing required field")
        self.assertTrue(any("policy_repr" in reason for reason in result.reasons))

    def test_every_required_field_is_individually_required(self):
        """One dropped field at a time, so no single check carries the whole suite."""
        required = ["schema", "seq", "request_id", "timestamp", "decision",
                    "policy_hash", "policy_repr", "input_hash", "prev_hash",
                    "violations", "metadata", "entry_hash"]
        for field in required:
            with self.subTest(field=field):
                package = copy_reference_package(self.tmp / f"drop-{field}")
                records = read_records(package)
                records[0].pop(field)
                write_records(package, records)
                # entry_hash is the integrity value: recomputing it would put it
                # straight back, so that case is only re-manifested.
                if field == "entry_hash":
                    refresh_manifest(package)
                else:
                    seal_records_only(package)
                self.assertEqual(INVALID, verify_package(package).status,
                                 f"dropping {field} did not yield INVALID")

    def test_wrong_field_type_is_invalid(self):
        self.mutate_and_reseal(0, lambda r: r.update(seq="0"))
        self.assertStatus(INVALID, "seq as a string")

    def test_wrong_type_for_each_kind_of_field(self):
        for field, value in (("seq", "0"), ("request_id", 7), ("timestamp", 20260827),
                             ("violations", {}), ("metadata", []), ("decision", 7),
                             ("decision", None), ("shadow_hash", 1),
                             ("prev_hash", 0), ("entry_hash", 12345)):
            with self.subTest(field=field, value=value):
                package = copy_reference_package(
                    self.tmp / f"type-{field}-{type(value).__name__}")
                records = read_records(package)
                records[1][field] = value
                write_records(package, records)
                # Recomputing entry_hash would overwrite the very value under test.
                if field == "entry_hash":
                    refresh_manifest(package)
                else:
                    seal_records_only(package)
                self.assertEqual(INVALID, verify_package(package).status,
                                 f"{field}={value!r} did not yield INVALID")

    def test_bool_is_not_an_integer_field(self):
        """bool subclasses int; true must not pass as a sequence number."""
        self.mutate_and_reseal(0, lambda r: r.update(seq=True))
        self.assertStatus(INVALID, "seq as bool")

    def test_violation_structure_is_validated(self):
        for label, violation in (
            ("missing action", {"rule": "R", "confidence": 1}),
            ("wrong confidence type", {"rule": "R", "action": "A", "confidence": "1"}),
            ("unknown violation field", {"rule": "R", "action": "A", "confidence": 1,
                                         "extra": "x"}),
            ("not an object", ["R", "A", 1]),
        ):
            with self.subTest(case=label):
                package = copy_reference_package(self.tmp / f"viol-{label.replace(' ','-')}")
                records = read_records(package)
                records[1]["violations"][0] = violation
                write_records(package, records)
                reseal_chain(package)
                self.assertEqual(INVALID, verify_package(package).status,
                                 f"{label} did not yield INVALID")

    def test_metadata_values_must_be_strings(self):
        self.mutate_and_reseal(0, lambda r: r.update(metadata={"actor": 17}))
        self.assertStatus(INVALID, "non-string metadata value")

    def test_schema_validation_runs_before_hashing(self):
        """An invalid record must not be able to reach an integrity verdict.

        The record here is internally consistent -- it hashes correctly over its own
        wrong member set -- so only a check that runs *before* hashing can catch it.
        """
        self.mutate_and_reseal(0, lambda r: r.pop("shadow_hash", None) or r.pop("metadata"))
        result = self.assertStatus(INVALID, "structurally invalid but self-consistent")
        self.assertFalse(any("entry_hash does not match" in r for r in result.reasons),
                         "the record was hashed before its structure was validated")


class P0R2UnknownFieldTest(_PackageCase):
    """M0 is a closed world: an unknown field cannot enter the protected domain."""

    def test_unknown_field_cannot_obtain_verified(self):
        """The record is correctly hashed over its own members and still INVALID.

        This is the regression the review asked for: before the fix this package
        reached VERIFIED, silently admitting an undeclared field into the evidence.
        """
        self.mutate_and_reseal(0, lambda r: r.update(injected_field="attacker data"))

        records = read_records(self.package)
        protected = {k: v for k, v in records[0].items() if k != "entry_hash"}
        import hashlib
        self.assertEqual(
            records[0]["entry_hash"],
            hashlib.sha256(canonical_bytes(protected)).hexdigest(),
            "precondition: the record must be correctly sealed over its own members",
        )

        result = self.assertStatus(INVALID, "unknown field")
        self.assertTrue(any("unknown field" in reason for reason in result.reasons),
                        result.reasons)

    def test_unknown_field_is_invalid_not_tampered(self):
        """The states stay distinct: this is unreadable, not altered."""
        self.mutate_and_reseal(1, lambda r: r.update(extension="v2"))
        self.assertNotEqual(TAMPERED, verify_package(self.package).status)
        self.assertStatus(INVALID, "unknown field classification")

    def test_no_extension_mechanism_exists(self):
        """Plausible extension spellings are all rejected, not special-cased."""
        for field in ("ext", "_ext", "x-vendor", "aura_ext", "__meta__", "v2_fields"):
            with self.subTest(field=field):
                package = copy_reference_package(self.tmp / f"ext-{field}")
                records = read_records(package)
                records[0][field] = "x"
                write_records(package, records)
                reseal_chain(package)
                self.assertEqual(INVALID, verify_package(package).status)


class P0R3ManifestSemanticsTest(_PackageCase):
    """The manifest declares a verification contract; it is checked, not just present."""

    UNSUPPORTED = {
        "profile": "aura.evidence.package/9",
        "audit_schema": "aura.audit/99",
        "canonical_form": "AURA-CANON/9",
        "digest": "MD5",
    }

    def rewrite_manifest(self, package: Path, **changes):
        path = package / "manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        for key, value in changes.items():
            if value is None:
                manifest.pop(key, None)
            else:
                manifest[key] = value
        path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
        refresh_manifest(package)

    def test_unsupported_declaration_is_invalid(self):
        for name, unsupported in self.UNSUPPORTED.items():
            with self.subTest(declaration=name):
                package = copy_reference_package(self.tmp / f"decl-{name}")
                self.rewrite_manifest(package, **{name: unsupported})
                result = verify_package(package)
                self.assertEqual(INVALID, result.status,
                                 f"{name}={unsupported!r} did not yield INVALID")
                self.assertTrue(any(name in reason for reason in result.reasons),
                                result.reasons)

    def test_missing_declaration_is_invalid(self):
        for name in self.UNSUPPORTED:
            with self.subTest(declaration=name):
                package = copy_reference_package(self.tmp / f"drop-{name}")
                self.rewrite_manifest(package, **{name: None})
                self.assertEqual(INVALID, verify_package(package).status,
                                 f"missing {name} did not yield INVALID")

    def test_supported_declarations_are_accepted(self):
        """The check must not reject the contract the repository actually implements."""
        self.assertStatus(VERIFIED, "reference package declarations")

    def test_declared_contract_matches_the_repository_constants(self):
        """The verifier's supported set must track core/, not a second copy."""
        from app.verifier import DECLARED_CONTRACT
        from core import (M0_AUDIT_SCHEMA, M0_CANONICAL_FORM, M0_DIGEST,
                          M0_PACKAGE_PROFILE)

        self.assertEqual(
            {"profile": M0_PACKAGE_PROFILE, "audit_schema": M0_AUDIT_SCHEMA,
             "canonical_form": M0_CANONICAL_FORM, "digest": M0_DIGEST},
            DECLARED_CONTRACT,
        )
        manifest = json.loads(
            (self.package / "manifest.json").read_text(encoding="utf-8")
        )
        for name, supported in DECLARED_CONTRACT.items():
            self.assertEqual(supported, manifest[name])


class P0R4LoneSurrogateTest(unittest.TestCase):
    """A lone surrogate has no UTF-8 encoding and therefore no canonical form."""

    SURROGATES = ["\ud800", "\udbff", "\udc00", "\udfff"]

    def test_lone_surrogate_in_a_value_raises_canonicalisation_error(self):
        for surrogate in self.SURROGATES:
            with self.subTest(codepoint=f"U+{ord(surrogate):04X}"):
                with self.assertRaises(CanonicalisationError):
                    canonical_bytes({"x": surrogate})

    def test_lone_surrogate_in_a_member_name_raises_canonicalisation_error(self):
        """Member names are checked before the UTF-16 sort key touches them.

        The sort key encodes to UTF-16-BE, which raises UnicodeEncodeError on a lone
        surrogate. Validating after sorting would let that error escape first.
        """
        for surrogate in self.SURROGATES:
            with self.subTest(codepoint=f"U+{ord(surrogate):04X}"):
                with self.assertRaises(CanonicalisationError):
                    canonical_bytes({surrogate: "y"})

    def test_lone_surrogate_nested_in_a_violation_raises(self):
        with self.assertRaises(CanonicalisationError):
            canonical_bytes({"violations": [{"rule": "R\ud800"}]})

    def test_no_unicode_encode_error_escapes_the_boundary(self):
        """The failure mode the review named: an implementation error leaking out."""
        for value in ({"x": "a\ud800b"}, {"\udfff": "y"}, {"a": ["\udc00"]}):
            with self.subTest(value=repr(value)):
                try:
                    canonical_bytes(value)
                except CanonicalisationError:
                    pass
                except UnicodeEncodeError as exc:
                    self.fail(f"UnicodeEncodeError escaped canonicalisation: {exc}")

    def test_surrogate_reaching_the_verifier_is_invalid(self):
        """A JSON escape for a lone surrogate is valid file content, so this path
        is reachable from a package on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            package = copy_reference_package(Path(tmp))
            records = read_records(package)
            records[0]["policy_repr"] = "loan\ud800"
            payload = "\n".join(
                json.dumps(r, sort_keys=True, separators=(",", ":"))
                for r in records
            ) + "\n"
            (package / "evidence/audit.jsonl").write_text(payload, encoding="utf-8")
            refresh_manifest(package)
            self.assertEqual(INVALID, verify_package(package).status)

    def test_valid_unicode_is_unaffected(self):
        """The fix must not change AURA-CANON/1 for anything with a canonical form."""
        self.assertEqual(
            '{"u":"é中\U0001F510"}'.encode("utf-8"),
            canonical_bytes({"u": "é中\U0001F510"}),
        )

    def test_a_valid_surrogate_pair_is_one_character_and_is_accepted(self):
        """U+1F510 is encoded in Python as a single character, not a pair, and must
        not be caught by a check aimed at lone surrogates."""
        self.assertIn("\U0001F510".encode("utf-8"), canonical_bytes({"k": "\U0001F510"}))


class P0R5ExpectedResultSemanticsTest(_PackageCase):
    """expected/result.json is non-normative test fixture metadata (Option A).

    Contract section 6.2. The verifier never reads it; a package's own claim about
    its verdict has no bearing on the verdict it receives.
    """

    def test_expected_result_is_not_a_required_file(self):
        from app.verifier import REQUIRED_FILES
        self.assertNotIn("expected/result.json", REQUIRED_FILES)

    def test_expected_result_is_not_bound_by_the_manifest(self):
        manifest = json.loads(
            (self.package / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("expected/result.json", manifest["files"],
                         "non-normative metadata must not be digest-bound as evidence")

    def test_a_contradictory_expected_result_does_not_change_the_verdict(self):
        """The package claims TAMPERED; the evidence says otherwise, and wins."""
        (self.package / "expected/result.json").write_text(
            json.dumps({"status": "TAMPERED", "package_id": "aura-evidence-loan-001",
                        "entries": 3, "reasons": ["fabricated"]}, indent=2) + "\n",
            encoding="utf-8")
        self.assertStatus(VERIFIED, "contradictory expected/result.json")

    def test_a_package_cannot_claim_verified_for_tampered_evidence(self):
        """The inverse, which is the direction that would actually matter."""
        records = read_records(self.package)
        records[0]["decision"] = "DENY"
        write_records(self.package, records)
        refresh_manifest(self.package)
        (self.package / "expected/result.json").write_text(
            json.dumps({"status": "VERIFIED", "package_id": "aura-evidence-loan-001",
                        "entries": 3, "reasons": []}, indent=2) + "\n",
            encoding="utf-8")
        self.assertStatus(TAMPERED, "expected/result.json claiming VERIFIED")

    def test_deleting_expected_result_does_not_change_the_verdict(self):
        (self.package / "expected/result.json").unlink()
        self.assertStatus(VERIFIED, "expected/result.json removed")

    def test_malformed_expected_result_does_not_change_the_verdict(self):
        (self.package / "expected/result.json").write_text("{ not json",
                                                           encoding="utf-8")
        self.assertStatus(VERIFIED, "malformed expected/result.json")

    def test_the_contract_states_the_interpretation(self):
        contract = (Path(__file__).resolve().parents[2]
                    / "docs/contract/M0-EVIDENCE-CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("`expected/result.json` is non-normative", contract)


class ClassificationSeparationTest(_PackageCase):
    """The new INVALID cases must not have absorbed TAMPERED or VERIFIED."""

    def test_all_three_states_remain_reachable(self):
        observed = {verify_package(self.package).status}

        tampered = copy_reference_package(self.tmp / "tampered")
        records = read_records(tampered)
        records[0]["decision"] = "DENY"
        write_records(tampered, records)
        refresh_manifest(tampered)
        observed.add(verify_package(tampered).status)

        invalid = copy_reference_package(self.tmp / "invalid")
        records = read_records(invalid)
        records[0]["unknown"] = "x"
        write_records(invalid, records)
        reseal_chain(invalid)
        observed.add(verify_package(invalid).status)

        self.assertEqual({VERIFIED, TAMPERED, INVALID}, observed)

    def test_value_domain_changes_remain_tampered_not_invalid(self):
        """Structure decides interpretability; the digest decides integrity.

        A decision, digest or timestamp altered to another well-typed value is a
        mutation of protected content, and must stay TAMPERED. Structural validation
        must not have quietly reclassified these.
        """
        for field, value in (("decision", "DENY"), ("policy_hash", "f" * 64),
                             ("timestamp", "2026-08-27T09:15:01Z"),
                             ("request_id", "other"), ("input_hash", "e" * 64)):
            with self.subTest(field=field):
                package = copy_reference_package(self.tmp / f"tam-{field}")
                records = read_records(package)
                records[0][field] = value
                write_records(package, records)
                refresh_manifest(package)
                self.assertEqual(TAMPERED, verify_package(package).status,
                                 f"{field} mutation was reclassified")


class SchemaValidatorUnitTest(unittest.TestCase):
    """The validator itself, independent of a package."""

    def record(self, **overrides) -> dict:
        base = {
            "schema": "aura.audit/1", "seq": 0, "request_id": "r",
            "timestamp": "2026-08-27T10:00:00Z", "decision": "ALLOW",
            "policy_hash": "a" * 64, "policy_repr": "p", "input_hash": "b" * 64,
            "prev_hash": "0" * 64, "violations": [], "metadata": {},
            "entry_hash": "c" * 64,
        }
        base.update(overrides)
        return base

    def test_a_well_formed_record_validates(self):
        validate_audit_record(self.record())

    def test_optional_shadow_hash_is_accepted_present_or_absent(self):
        validate_audit_record(self.record())
        validate_audit_record(self.record(shadow_hash="d" * 64))

    def test_schema_error_is_a_model_error(self):
        """So existing callers catching ModelError keep working."""
        from core.models import ModelError
        self.assertTrue(issubclass(SchemaError, ModelError))

    def test_non_object_record_is_rejected(self):
        for value in ([], "record", 7, None):
            with self.subTest(value=value):
                with self.assertRaises(SchemaError):
                    validate_audit_record(value)


if __name__ == "__main__":
    unittest.main()
