"""P0-R6 -- the semantic AuditEntry domain.

Three layers, and only the third is about integrity:

    structural interpretability   presence, type, closed world, supported schema
    semantic AuditEntry domain    decision vocabulary, timestamp domain, hash
                                  representation, sequence domain, non-empty
                                  identifiers, confidence domain
    integrity                     canonical bytes, SHA-256, chain linkage,
                                  policy binding

The first two decide whether the thing is an M0 AuditEntry at all, and both are
INVALID. Only the third yields TAMPERED, and only for a record that is already a
valid AuditEntry whose protected content no longer matches its committed binding.

Reproduced on 6d28400, each record correctly resealed and its manifest repaired:

    decision   = "WHATEVER"  -> VERIFIED       timestamp  = "garbage" -> VERIFIED
    input_hash = "xyz"       -> VERIFIED       shadow_hash= "xyz"     -> VERIFIED
    request_id = ""          -> VERIFIED       confidence = -1        -> VERIFIED
    confidence = 10001       -> VERIFIED
    policy_hash= "xyz"       -> TAMPERED  (incidentally: policy-binding cross-check)
    prev_hash  = "xyz"       -> TAMPERED  (incidentally: chain link)
    seq        = -1          -> TAMPERED  (incidentally: chain position)

Seven reached VERIFIED. The three that did not were caught by unrelated checks
that happened to fire, not because any value domain was examined -- and they were
reported as TAMPERED, which claims the record is evidence when it is not.

Being hashable is not being interpretable. A record carrying a decision M0 does
not define can be canonicalised, sealed with a correct digest, and linked into a
chain; it would then present as intact evidence for a decision that has no
meaning in this system.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _m0 import (copy_reference_package, read_records, refresh_manifest,
                 write_records)

from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package
from core.canonical import canonical_bytes
from core.models import (CONFIDENCE_SCALE, DECISIONS, SchemaError,
                         validate_audit_record, validate_audit_semantics)


def seal_entry_hashes(package: Path) -> None:
    """Recompute each record's entry_hash over its own members, without relinking.

    ``reseal_chain`` also rewrites prev_hash, which would restore the very value
    some of these tests put under examination. This is the strongest adversarial
    posture the request asks for: the record is left semantically invalid but
    cryptographically self-consistent, and the manifest is repaired, so nothing
    but a value-domain check can reject it.
    """
    records = read_records(package)
    for record in records:
        protected = {k: v for k, v in record.items() if k != "entry_hash"}
        record["entry_hash"] = hashlib.sha256(canonical_bytes(protected)).hexdigest()
    write_records(package, records)
    refresh_manifest(package)


class _SemanticCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._built = 0

    def sealed_with(self, index: int, mutate, *, reseal: bool = True) -> Path:
        """A package whose record ``index`` is mutated, then correctly resealed."""
        self._built += 1
        package = copy_reference_package(self.tmp / f"case{self._built}")
        records = read_records(package)
        mutate(records[index])
        write_records(package, records)
        if reseal:
            seal_entry_hashes(package)
        else:
            refresh_manifest(package)
        return package

    def assertSemanticallyRefused(self, package: Path, note: str):
        result = verify_package(package)
        self.assertEqual(
            INVALID, result.status,
            f"{note}: expected INVALID, got {result.status} ({result.reasons})",
        )
        self.assertNotEqual(
            TAMPERED, result.status,
            f"{note}: a record outside the M0 value domain is not evidence that was "
            f"altered -- it is not an M0 AuditEntry",
        )
        self.assertTrue(result.reasons, f"{note}: INVALID with no stated reason")
        return result


class DecisionVocabularyTest(_SemanticCase):
    def test_unknown_decision_is_invalid(self):
        package = self.sealed_with(0, lambda r: r.update(decision="WHATEVER"))
        self.assertSemanticallyRefused(package, 'decision "WHATEVER"')

    def test_decision_vocabulary_is_closed(self):
        for value in ("whatever", "allow", "Allow", "ALLOW ", "", "PERMIT", "DENIED"):
            with self.subTest(decision=value):
                package = self.sealed_with(0, lambda r, v=value: r.update(decision=v))
                self.assertSemanticallyRefused(package, f"decision {value!r}")

    def test_every_defined_decision_remains_acceptable(self):
        """The check must not reject the vocabulary M0 actually defines."""
        for value in DECISIONS:
            with self.subTest(decision=value):
                package = self.sealed_with(0, lambda r, v=value: r.update(decision=v))
                # Resealing record 0 breaks the chain link for record 1, so the
                # verdict is TAMPERED -- but never INVALID, which is the point.
                self.assertNotEqual(INVALID, verify_package(package).status)


class TimestampDomainTest(_SemanticCase):
    def test_garbage_timestamp_is_invalid(self):
        package = self.sealed_with(0, lambda r: r.update(timestamp="garbage"))
        self.assertSemanticallyRefused(package, 'timestamp "garbage"')

    def test_only_one_spelling_of_an_instant_is_accepted(self):
        """Offsets, fractional seconds, and space separators are other spellings.

        Admitting them would let one instant have several canonical byte strings
        and therefore several digests.
        """
        for value in ("2026-08-27T09:15:00+00:00", "2026-08-27T09:15:00.000Z",
                      "2026-08-27 09:15:00Z", "2026-08-27T09:15:00",
                      "20260827T091500Z", "", "2026-08-27"):
            with self.subTest(timestamp=value):
                package = self.sealed_with(0, lambda r, v=value: r.update(timestamp=v))
                self.assertSemanticallyRefused(package, f"timestamp {value!r}")


class HashRepresentationTest(_SemanticCase):
    def test_non_hex_digest_fields_are_invalid(self):
        for name in ("policy_hash", "input_hash", "prev_hash"):
            with self.subTest(field=name):
                package = self.sealed_with(0, lambda r, n=name: r.update(**{n: "xyz"}))
                self.assertSemanticallyRefused(package, f"{name} = 'xyz'")

    def test_non_hex_shadow_hash_is_invalid(self):
        package = self.sealed_with(1, lambda r: r.update(shadow_hash="xyz"))
        self.assertSemanticallyRefused(package, "shadow_hash = 'xyz'")

    def test_digest_representation_is_exactly_64_lowercase_hex(self):
        for value in ("", "abc", "A" * 64, "a" * 63, "a" * 65, "g" * 64,
                      "0x" + "a" * 62, " " + "a" * 63):
            with self.subTest(policy_hash=value):
                package = self.sealed_with(0, lambda r, v=value: r.update(policy_hash=v))
                self.assertSemanticallyRefused(package, f"policy_hash {value!r}")

    def test_non_hex_entry_hash_is_invalid(self):
        """The integrity value itself must look like an M0 digest.

        Not resealed: recomputing entry_hash would overwrite the value under test.
        """
        package = self.sealed_with(0, lambda r: r.update(entry_hash="xyz"),
                                   reseal=False)
        self.assertSemanticallyRefused(package, "entry_hash = 'xyz'")

    def test_a_wrong_but_well_formed_digest_stays_tampered(self):
        """The boundary: 64 hex characters that are simply wrong is tampering."""
        package = self.sealed_with(0, lambda r: r.update(entry_hash="0" * 64),
                                   reseal=False)
        self.assertEqual(TAMPERED, verify_package(package).status)


class SequenceDomainTest(_SemanticCase):
    def test_negative_sequence_is_invalid(self):
        package = self.sealed_with(0, lambda r: r.update(seq=-1))
        self.assertSemanticallyRefused(package, "seq = -1")

    def test_negative_sequence_is_invalid_not_merely_out_of_position(self):
        """Distinguish the domain from the chain-position check.

        seq = -1 was already rejected before this change, but as TAMPERED, by the
        position invariant. A negative sequence number is not a misplaced entry;
        it is not a sequence number.
        """
        package = self.sealed_with(0, lambda r: r.update(seq=-5))
        result = self.assertSemanticallyRefused(package, "seq = -5")
        self.assertTrue(any("seq" in reason for reason in result.reasons), result.reasons)

    def test_a_non_negative_but_wrong_sequence_stays_tampered(self):
        package = self.sealed_with(0, lambda r: r.update(seq=7))
        self.assertEqual(TAMPERED, verify_package(package).status)


class RequiredNonEmptyTest(_SemanticCase):
    def test_empty_request_id_is_invalid(self):
        package = self.sealed_with(0, lambda r: r.update(request_id=""))
        self.assertSemanticallyRefused(package, "request_id = ''")

    def test_empty_violation_rule_or_action_is_invalid(self):
        for field in ("rule", "action"):
            with self.subTest(field=field):
                package = self.sealed_with(
                    1, lambda r, f=field: r["violations"][0].update(**{f: ""})
                )
                self.assertSemanticallyRefused(package, f"violation.{field} = ''")

    def test_policy_repr_may_be_empty(self):
        """The contract says policy_repr may be empty; the check must not overreach."""
        package = self.sealed_with(0, lambda r: r.update(policy_repr=""))
        self.assertNotEqual(INVALID, verify_package(package).status)


class ConfidenceDomainTest(_SemanticCase):
    def test_negative_confidence_is_invalid(self):
        package = self.sealed_with(1, lambda r: r["violations"][0].update(confidence=-1))
        self.assertSemanticallyRefused(package, "confidence = -1")

    def test_confidence_above_scale_is_invalid(self):
        package = self.sealed_with(
            1, lambda r: r["violations"][0].update(confidence=CONFIDENCE_SCALE + 1)
        )
        self.assertSemanticallyRefused(package, f"confidence = {CONFIDENCE_SCALE + 1}")

    def test_the_confidence_boundaries_themselves_remain_acceptable(self):
        for value in (0, CONFIDENCE_SCALE):
            with self.subTest(confidence=value):
                package = self.sealed_with(
                    1, lambda r, v=value: r["violations"][0].update(confidence=v)
                )
                self.assertNotEqual(INVALID, verify_package(package).status)


class AdversarialResealTest(_SemanticCase):
    """Requirement C: semantically invalid, correctly sealed, manifest repaired."""

    def test_a_correctly_sealed_invalid_record_does_not_verify(self):
        package = self.sealed_with(0, lambda r: r.update(decision="WHATEVER"))

        # Preconditions: the record really is cryptographically self-consistent and
        # the manifest really does match the bytes on disk. Without these the test
        # would be proving a digest mismatch, not a value-domain rejection.
        records = read_records(package)
        protected = {k: v for k, v in records[0].items() if k != "entry_hash"}
        self.assertEqual(
            records[0]["entry_hash"],
            hashlib.sha256(canonical_bytes(protected)).hexdigest(),
            "precondition: the record must be correctly sealed over its own members",
        )
        manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
        for relative, expected in manifest["files"].items():
            self.assertEqual(
                expected,
                hashlib.sha256((package / relative).read_bytes()).hexdigest(),
                "precondition: the manifest must match the files on disk",
            )

        result = verify_package(package)
        self.assertNotEqual(VERIFIED, result.status)
        self.assertEqual(INVALID, result.status, result.reasons)

    def test_every_listed_semantic_case_refuses_when_correctly_sealed(self):
        """The ten cases the change request names, each fully repaired."""
        cases = [
            (0, "decision", "WHATEVER"), (0, "timestamp", "garbage"),
            (0, "policy_hash", "xyz"), (0, "input_hash", "xyz"),
            (0, "prev_hash", "xyz"), (1, "shadow_hash", "xyz"),
            (0, "seq", -1), (0, "request_id", ""),
        ]
        for index, field, value in cases:
            with self.subTest(field=field, value=value):
                package = self.sealed_with(
                    index, lambda r, f=field, v=value: r.update(**{f: v})
                )
                self.assertSemanticallyRefused(package, f"{field} = {value!r}")

        for value in (-1, CONFIDENCE_SCALE + 1):
            with self.subTest(confidence=value):
                package = self.sealed_with(
                    1, lambda r, v=value: r["violations"][0].update(confidence=v)
                )
                self.assertSemanticallyRefused(package, f"confidence = {value}")


class ClassificationPreservedTest(_SemanticCase):
    """Requirement D: the existing three classifications are untouched."""

    def test_pristine_package_verifies(self):
        package = copy_reference_package(self.tmp / "pristine")
        result = verify_package(package)
        self.assertEqual(VERIFIED, result.status, result.reasons)
        self.assertEqual(3, result.entries)

    def test_mutation_within_the_value_domain_is_still_tampered(self):
        """Replacing a valid value with another valid value is still tampering.

        This is the boundary the semantic layer must not swallow: every one of
        these is a well-formed AuditEntry, so the failure is of integrity.
        """
        for field, value in (("decision", "DENY"), ("policy_hash", "f" * 64),
                             ("input_hash", "e" * 64),
                             ("timestamp", "2026-08-27T09:15:01Z"),
                             ("request_id", "other"), ("seq", 2)):
            with self.subTest(field=field, value=value):
                package = self.sealed_with(
                    0, lambda r, f=field, v=value: r.update(**{f: v}), reseal=False
                )
                self.assertEqual(
                    TAMPERED, verify_package(package).status,
                    f"{field}={value!r} was reclassified away from TAMPERED",
                )

    def test_malformed_package_is_still_invalid(self):
        package = copy_reference_package(self.tmp / "malformed")
        (package / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual(INVALID, verify_package(package).status)

    def test_all_three_states_remain_reachable(self):
        verified = copy_reference_package(self.tmp / "s-verified")

        tampered = self.sealed_with(0, lambda r: r.update(decision="DENY"),
                                    reseal=False)
        invalid = self.sealed_with(0, lambda r: r.update(decision="WHATEVER"))

        self.assertEqual(
            {VERIFIED, TAMPERED, INVALID},
            {verify_package(p).status for p in (verified, tampered, invalid)},
        )


class SemanticValidatorUnitTest(unittest.TestCase):
    """The validator itself, independent of a package."""

    def record(self, **overrides) -> dict:
        base = {
            "schema": "aura.audit/1", "seq": 0, "request_id": "r",
            "timestamp": "2026-08-27T10:00:00Z", "decision": "ALLOW",
            "policy_hash": "a" * 64, "policy_repr": "", "input_hash": "b" * 64,
            "prev_hash": "0" * 64, "violations": [], "metadata": {},
            "entry_hash": "c" * 64,
        }
        base.update(overrides)
        return base

    def test_a_valid_record_passes_both_layers(self):
        record = self.record()
        validate_audit_record(record)
        validate_audit_semantics(record)

    def test_semantics_are_a_separate_layer_from_structure(self):
        """A structurally perfect record can still be semantically invalid.

        If structure alone were sufficient, this record would pass -- which is
        exactly the gap P0-R6 closes.
        """
        record = self.record(decision="WHATEVER")
        validate_audit_record(record)  # layer 1 passes
        with self.assertRaises(SchemaError):
            validate_audit_semantics(record)  # layer 2 does not

    def test_optional_shadow_hash_is_checked_only_when_present(self):
        validate_audit_semantics(self.record())
        validate_audit_semantics(self.record(shadow_hash="d" * 64))
        with self.assertRaises(SchemaError):
            validate_audit_semantics(self.record(shadow_hash="xyz"))

    def test_the_error_names_the_offending_member(self):
        for field, value in (("decision", "WHATEVER"), ("timestamp", "garbage"),
                             ("input_hash", "xyz"), ("seq", -1)):
            with self.subTest(field=field):
                with self.assertRaises(SchemaError) as caught:
                    validate_audit_semantics(self.record(**{field: value}))
                self.assertIn(field, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
