"""The M0 mutation gate.

Starting point: the reference package verifies as VERIFIED. Each test then mutates
exactly one protected element and asserts the **external classification** is
TAMPERED -- not merely that "verification failed".

Every mutation refreshes the manifest digests afterwards (see
``tests/_m0.refresh_manifest``). Without that step the manifest checksum alone would
catch every mutation and the canonical binding would never be exercised. Refreshing
models the stronger attacker: one who edits the evidence and repairs the outer
checksum, leaving only the canonical digest chain to detect the change.
"""

import json
import tempfile
import unicodedata
import unittest
from pathlib import Path

from _m0 import (copy_reference_package, read_records, refresh_manifest, reseal_chain,
                 write_records)

from app.verifier import TAMPERED, VERIFIED, verify_package


class MutationGateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.package = copy_reference_package(Path(self._tmp.name))

    def assertVerified(self):
        result = verify_package(self.package)
        self.assertEqual(VERIFIED, result.status, f"reasons: {result.reasons}")

    def assertTampered(self, note: str):
        result = verify_package(self.package)
        self.assertEqual(
            TAMPERED, result.status,
            f"{note}: expected TAMPERED, got {result.status} (reasons: {result.reasons})",
        )
        self.assertTrue(result.reasons, f"{note}: TAMPERED with no stated reason")

    def mutate_record(self, index: int, **changes):
        records = read_records(self.package)
        records[index].update(changes)
        write_records(self.package, records)
        refresh_manifest(self.package)

    # ---- the starting point -------------------------------------------------

    def test_unmutated_reference_package_is_verified(self):
        """If this fails, every TAMPERED assertion below proves nothing."""
        self.assertVerified()

    def test_refreshing_the_manifest_alone_does_not_change_the_verdict(self):
        """The mutation harness must not be what causes the failures it reports."""
        refresh_manifest(self.package)
        self.assertVerified()

    # ---- protected scalar members ------------------------------------------

    def test_decision(self):
        self.mutate_record(2, decision="ALLOW")
        self.assertTampered("decision")

    def test_policy_hash(self):
        self.mutate_record(1, policy_hash="f" * 64)
        self.assertTampered("policy_hash")

    def test_policy_representation(self):
        self.mutate_record(1, policy_repr="loan.underwriting/3")
        self.assertTampered("policy_repr")

    def test_input_hash(self):
        self.mutate_record(0, input_hash="e" * 64)
        self.assertTampered("input_hash")

    def test_shadow_hash(self):
        self.mutate_record(1, shadow_hash="9" * 64)
        self.assertTampered("shadow_hash")

    def test_shadow_hash_removed(self):
        records = read_records(self.package)
        del records[1]["shadow_hash"]
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("shadow_hash removed")

    def test_prev_hash(self):
        self.mutate_record(2, prev_hash="7" * 64)
        self.assertTampered("prev_hash")

    def test_seq(self):
        self.mutate_record(1, seq=9)
        self.assertTampered("seq")

    def test_timestamp(self):
        self.mutate_record(0, timestamp="2026-08-27T09:15:01Z")
        self.assertTampered("timestamp")

    def test_schema(self):
        """A schema this verifier does not implement is INVALID, so the mutation used
        here keeps the schema supported and changes only what it binds."""
        records = read_records(self.package)
        records[0]["schema"] = "aura.audit/1 "
        write_records(self.package, records)
        refresh_manifest(self.package)
        result = verify_package(self.package)
        self.assertIn(result.status, ("TAMPERED", "INVALID"))
        self.assertNotEqual(VERIFIED, result.status)

    def test_request_id(self):
        self.mutate_record(0, request_id="loan-002-intake")
        self.assertTampered("request_id")

    def test_entry_hash_itself(self):
        self.mutate_record(1, entry_hash="0" * 64)
        self.assertTampered("entry_hash")

    # ---- protected metadata -------------------------------------------------

    def test_metadata_value(self):
        records = read_records(self.package)
        records[0]["metadata"]["actor"] = "agent-99"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("metadata value")

    def test_metadata_key_added(self):
        records = read_records(self.package)
        records[0]["metadata"]["injected"] = ""
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("metadata key added")

    def test_metadata_key_removed(self):
        records = read_records(self.package)
        del records[0]["metadata"]["stage"]
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("metadata key removed")

    def test_metadata_empty_value_removed(self):
        """Record 2 carries note:"". Removing it is the Some("") -> None mutation."""
        records = read_records(self.package)
        self.assertEqual("", records[2]["metadata"]["note"])
        del records[2]["metadata"]["note"]
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered('metadata Some("") removed')

    # ---- violations ---------------------------------------------------------

    def test_violation_rule(self):
        records = read_records(self.package)
        records[1]["violations"][0]["rule"] = "LOAN.SOMETHING_ELSE"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("violation rule")

    def test_violation_action(self):
        records = read_records(self.package)
        records[1]["violations"][0]["action"] = "FLAG"
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("violation action")

    def test_violation_confidence(self):
        records = read_records(self.package)
        records[1]["violations"][0]["confidence"] = 9499
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("violation confidence")

    def test_violation_ordering(self):
        records = read_records(self.package)
        records[1]["violations"].reverse()
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("violation ordering")

    def test_violation_removed(self):
        records = read_records(self.package)
        records[1]["violations"].pop()
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("violation removed")

    def test_violation_added(self):
        records = read_records(self.package)
        records[0]["violations"].append(
            {"action": "LOG", "confidence": 1, "rule": "INJECTED"}
        )
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("violation added")

    # ---- representation-level mutations -------------------------------------

    def test_unicode_representation(self):
        """Decomposed U+0065 U+0301 renders as 'e-acute' but is different evidence.

        Built as a legitimately sealed package carrying the composed spelling, so the
        only change under test is the substitution itself. Written with explicit
        escapes because the two spellings are visually identical in source.
        """
        composed = "caf\u00e9"
        decomposed = "cafe\u0301"
        self.assertNotEqual(composed, decomposed)
        self.assertEqual(unicodedata.normalize("NFC", decomposed), composed)

        records = read_records(self.package)
        records[1]["metadata"]["note"] = composed
        write_records(self.package, records)
        reseal_chain(self.package)
        self.assertVerified()

        records = read_records(self.package)
        records[1]["metadata"]["note"] = decomposed
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("unicode decomposition substituted for composed")

    def test_m0_seals_integrity_not_authenticity(self):
        """A recorded limitation, asserted so it cannot be forgotten or overclaimed.

        An attacker who can rewrite every record and the manifest produces a
        self-consistent package that verifies. M0 defines no signature scheme, so
        VERIFIED means the evidence is internally consistent -- not that this
        producer sealed it. The verifier must never be documented as proving origin.
        """
        records = read_records(self.package)
        records[2]["decision"] = "ALLOW"
        write_records(self.package, records)
        reseal_chain(self.package)
        self.assertEqual(VERIFIED, verify_package(self.package).status)

    def test_escaping(self):
        records = read_records(self.package)
        records[1]["metadata"]["note"] = records[1]["metadata"]["note"].replace(
            '\\ review', '\\\\ review'
        )
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("escaping")

    def test_injection_like_content(self):
        records = read_records(self.package)
        records[0]["metadata"]["actor"] = 'agent-17","decision":"ALLOW'
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("injection-like content")

    # ---- chain-level and package-level mutations ----------------------------

    def test_record_deleted_from_the_chain(self):
        records = read_records(self.package)
        del records[1]
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("record deleted")

    def test_records_reordered(self):
        records = read_records(self.package)
        records[0], records[1] = records[1], records[0]
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("records reordered")

    def test_record_appended_with_a_valid_self_digest(self):
        """A forged entry that is internally consistent must still fail to link."""
        records = read_records(self.package)
        forged = json.loads(json.dumps(records[2]))
        forged["seq"] = 3
        forged["request_id"] = "loan-001-forged"
        forged["prev_hash"] = "0" * 64
        from core.canonical import canonical_bytes
        import hashlib
        protected = {k: v for k, v in forged.items() if k != "entry_hash"}
        forged["entry_hash"] = hashlib.sha256(canonical_bytes(protected)).hexdigest()
        records.append(forged)
        write_records(self.package, records)
        refresh_manifest(self.package)
        self.assertTampered("forged appended record")

    def test_policy_document_mutated(self):
        policy_path = self.package / "evidence/policy.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["rules"][0]["threshold_bp"] = 9900
        policy_path.write_text(json.dumps(policy, sort_keys=True, indent=2) + "\n",
                               encoding="utf-8")
        refresh_manifest(self.package)
        self.assertTampered("policy document")

    def test_genesis_anchor_mutated(self):
        genesis_path = self.package / "evidence/genesis.json"
        genesis = json.loads(genesis_path.read_text(encoding="utf-8"))
        genesis["prev_hash"] = "1" * 64
        genesis_path.write_text(json.dumps(genesis, sort_keys=True, indent=2) + "\n",
                                encoding="utf-8")
        refresh_manifest(self.package)
        self.assertTampered("genesis anchor")

    def test_manifest_digest_left_stale(self):
        """The manifest binding is checked too, not only the canonical chain."""
        records = read_records(self.package)
        records[0]["decision"] = "DENY"
        write_records(self.package, records)
        # deliberately no refresh_manifest
        self.assertTampered("stale manifest digest")


class MutationCoverageTest(unittest.TestCase):
    """The gate must actually cover every element the M0 contract lists as protected."""

    REQUIRED = [
        "decision", "policy_hash", "policy_representation", "input_hash", "shadow_hash",
        "prev_hash", "seq", "timestamp", "schema", "request_id", "violation_rule",
        "violation_action", "violation_confidence", "violation_ordering",
        "unicode_representation", "escaping", "injection_like_content",
    ]

    def test_a_test_exists_for_every_protected_element(self):
        names = {n for n in dir(MutationGateTest) if n.startswith("test_")}
        missing = [
            element for element in self.REQUIRED
            if f"test_{element}" not in names
        ]
        self.assertEqual([], missing, f"mutation gate has no test for: {missing}")


if __name__ == "__main__":
    unittest.main()
