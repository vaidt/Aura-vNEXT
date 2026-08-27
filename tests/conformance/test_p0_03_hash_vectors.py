"""P0-03 -- SHA-256 vectors over the canonical bytes.

    canonical bytes -> SHA-256 -> expected digest

and the two properties that make the digest evidence rather than a checksum:

    same semantic input  = same canonical bytes = same digest
    protected mutation  -> different canonical bytes -> different digest
"""

import hashlib
import unicodedata
import unittest
from decimal import Decimal

from _m0 import build_entry, load_vectors, vectors_by_name

from core.chain import entry_hash, entry_preimage, seal, verify_entry
from core.models import AuditEntry, Violation


class HashVectorTest(unittest.TestCase):
    def test_every_vector_reproduces_its_recorded_digest(self):
        for vector in load_vectors():
            with self.subTest(vector=vector["name"]):
                entry = build_entry(vector["input"])
                self.assertEqual(vector["sha256"], entry_hash(entry))

    def test_recorded_digest_is_the_digest_of_the_recorded_bytes(self):
        """Ties the P0-03 digest to the P0-02 bytes, not merely to the implementation."""
        for vector in load_vectors():
            with self.subTest(vector=vector["name"]):
                recorded = bytes.fromhex(vector["canonical_hex"])
                self.assertEqual(vector["sha256"], hashlib.sha256(recorded).hexdigest())

    def test_no_two_vectors_share_a_digest(self):
        seen: dict[str, str] = {}
        for vector in load_vectors():
            digest = entry_hash(build_entry(vector["input"]))
            self.assertNotIn(
                digest, seen, f"{vector['name']} collides with {seen.get(digest)}"
            )
            seen[digest] = vector["name"]

    def test_digest_is_sha256_and_not_some_other_primitive(self):
        vector = vectors_by_name()["minimal"]
        recorded = bytes.fromhex(vector["canonical_hex"])
        self.assertEqual(64, len(vector["sha256"]))
        self.assertEqual(hashlib.sha256(recorded).hexdigest(), vector["sha256"])
        self.assertNotEqual(hashlib.sha512(recorded).hexdigest()[:64], vector["sha256"])


class DeterminismTest(unittest.TestCase):
    """same semantic input = same canonical bytes = same digest."""

    def test_repeated_construction_is_byte_identical(self):
        for vector in load_vectors():
            with self.subTest(vector=vector["name"]):
                first = entry_preimage(build_entry(vector["input"]))
                second = entry_preimage(build_entry(vector["input"]))
                self.assertEqual(first, second)
                self.assertEqual(
                    hashlib.sha256(first).hexdigest(), hashlib.sha256(second).hexdigest()
                )

    def test_member_insertion_order_does_not_affect_the_bytes(self):
        """Map iteration order is a classic source of non-determinism (criterion C6)."""
        forward = AuditEntry(
            seq=1, request_id="r", timestamp="2026-08-27T10:00:00Z", decision="ALLOW",
            policy_hash="a" * 64, policy_repr="p", input_hash="b" * 64,
            prev_hash="c" * 64, metadata={"alpha": "1", "beta": "2", "gamma": "3"},
        )
        reversed_order = AuditEntry(
            seq=1, request_id="r", timestamp="2026-08-27T10:00:00Z", decision="ALLOW",
            policy_hash="a" * 64, policy_repr="p", input_hash="b" * 64,
            prev_hash="c" * 64, metadata={"gamma": "3", "beta": "2", "alpha": "1"},
        )
        self.assertEqual(entry_preimage(forward), entry_preimage(reversed_order))
        self.assertEqual(entry_hash(forward), entry_hash(reversed_order))

    def test_equivalent_confidence_spellings_produce_one_digest(self):
        """0.95, "0.95", and Decimal("0.95") are one value, so they are one digest."""
        digests = {
            entry_hash(AuditEntry(
                seq=0, request_id="r", timestamp="2026-08-27T10:00:00Z", decision="DENY",
                policy_hash="a" * 64, policy_repr="p", input_hash="b" * 64,
                prev_hash="0" * 64,
                violations=[Violation.build("R", "BLOCK", spelling)],
            ))
            for spelling in (0.95, "0.95", Decimal("0.95"), "0.9500")
        }
        self.assertEqual(1, len(digests), f"confidence spelling changed the digest: {digests}")


class ProtectedMutationTest(unittest.TestCase):
    """protected mutation -> different canonical bytes -> different digest."""

    BASE = dict(
        seq=4, request_id="req-mut", timestamp="2026-08-27T10:00:00Z",
        decision="REQUIRE_APPROVAL", policy_hash="a" * 64, policy_repr="loan/2",
        input_hash="b" * 64, prev_hash="c" * 64, shadow_hash="d" * 64,
        metadata={"actor": "agent-17"},
    )

    def entry(self, **overrides) -> AuditEntry:
        fields = dict(self.BASE)
        fields.setdefault(
            "violations", [Violation.build("RULE.A", "BLOCK", "0.25"),
                           Violation.build("RULE.B", "FLAG", "0.75")]
        )
        fields.update(overrides)
        return AuditEntry(**fields)

    MUTATIONS = {
        "decision": {"decision": "ALLOW"},
        "policy_hash": {"policy_hash": "f" * 64},
        "policy_repr": {"policy_repr": "loan/3"},
        "input_hash": {"input_hash": "e" * 64},
        "shadow_hash": {"shadow_hash": "0" * 64},
        "shadow_hash_removed": {"shadow_hash": None},
        "prev_hash": {"prev_hash": "9" * 64},
        "seq": {"seq": 5},
        "timestamp": {"timestamp": "2026-08-27T10:00:01Z"},
        "schema": {"schema": "aura.audit/99"},
        "request_id": {"request_id": "req-mut-2"},
        "metadata_value": {"metadata": {"actor": "agent-18"}},
        "metadata_key_added": {"metadata": {"actor": "agent-17", "extra": ""}},
        "metadata_removed": {"metadata": {}},
        "violation_rule": {"violations": [Violation.build("RULE.X", "BLOCK", "0.25"),
                                          Violation.build("RULE.B", "FLAG", "0.75")]},
        "violation_action": {"violations": [Violation.build("RULE.A", "FLAG", "0.25"),
                                            Violation.build("RULE.B", "FLAG", "0.75")]},
        "violation_confidence": {"violations": [Violation.build("RULE.A", "BLOCK", "0.26"),
                                                Violation.build("RULE.B", "FLAG", "0.75")]},
        "violation_ordering": {"violations": [Violation.build("RULE.B", "FLAG", "0.75"),
                                              Violation.build("RULE.A", "BLOCK", "0.25")]},
        "violation_removed": {"violations": [Violation.build("RULE.A", "BLOCK", "0.25")]},
        "violations_emptied": {"violations": []},
    }

    def test_every_protected_mutation_changes_bytes_and_digest(self):
        original = self.entry()
        original_bytes = entry_preimage(original)
        original_digest = entry_hash(original)

        for name, override in self.MUTATIONS.items():
            with self.subTest(mutation=name):
                mutated = self.entry(**override)
                self.assertNotEqual(
                    original_bytes, entry_preimage(mutated),
                    f"mutating {name} left the canonical bytes unchanged",
                )
                self.assertNotEqual(
                    original_digest, entry_hash(mutated),
                    f"mutating {name} left the digest unchanged",
                )

    def test_unicode_representation_change_is_a_mutation(self):
        """Two spellings of 'the same' text are two different pieces of evidence.

        U+00E9 and the decomposed U+0065 U+0301 render identically. M0 does not
        normalise: it binds the bytes the producer supplied, so a substitution is
        detected rather than silently accepted.
        """
        composed = self.entry(policy_repr="caf\u00e9")
        decomposed = self.entry(policy_repr="cafe\u0301")
        self.assertNotEqual(composed.policy_repr, decomposed.policy_repr)
        self.assertEqual(
            unicodedata.normalize("NFC", decomposed.policy_repr),
            composed.policy_repr,
            "the two spellings must render alike, or this tests nothing",
        )
        self.assertNotEqual(entry_preimage(composed), entry_preimage(decomposed))
        self.assertNotEqual(entry_hash(composed), entry_hash(decomposed))

    def test_escaping_change_is_a_mutation(self):
        plain = self.entry(policy_repr='a"b')
        escaped = self.entry(policy_repr='a\\"b')
        self.assertNotEqual(entry_preimage(plain), entry_preimage(escaped))
        self.assertNotEqual(entry_hash(plain), entry_hash(escaped))


class IntegrityFieldExclusionTest(unittest.TestCase):
    """The integrity value must not participate in its own preimage."""

    def entry(self) -> AuditEntry:
        return AuditEntry(
            seq=0, request_id="r", timestamp="2026-08-27T10:00:00Z", decision="ALLOW",
            policy_hash="a" * 64, policy_repr="p", input_hash="b" * 64,
            prev_hash="0" * 64,
        )

    def test_sealing_does_not_change_the_digest(self):
        """Attaching the digest to the record must not alter what the digest covers."""
        entry = self.entry()
        record = seal(entry)
        self.assertEqual(entry_hash(entry), record["entry_hash"])

        protected = {k: v for k, v in record.items() if k != "entry_hash"}
        self.assertEqual(entry.canonical_representation(), protected)

    def test_recomputation_from_the_wire_form_agrees(self):
        """A verifier works from the record, not from a producer-side object."""
        self.assertTrue(verify_entry(seal(self.entry())))

    def test_a_self_referential_preimage_would_be_detected(self):
        """Guard the property directly: hashing the sealed record must not reproduce
        the sealed record's own digest. If it ever did, the digest would be covering
        itself and the exclusion rule would have been broken."""
        record = seal(self.entry())
        from core.canonical import canonical_bytes
        self_referential = hashlib.sha256(canonical_bytes(record)).hexdigest()
        self.assertNotEqual(record["entry_hash"], self_referential)


if __name__ == "__main__":
    unittest.main()
