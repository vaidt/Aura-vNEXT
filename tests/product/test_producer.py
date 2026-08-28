"""The producer: an application event becomes a verifiable Evidence Package.

M0 established what evidence is and what a verifier may conclude. It did not
establish how an application obtains a package, which left hand-written fixtures as
the only source of evidence. These tests cover that path, and in particular the
property that makes it trustworthy: the producer computes nothing protected itself.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _m0 import REFERENCE_PACKAGE
from _product import LOAN_EVENTS, LOAN_POLICY, PACKAGE_ID, produce_loan_package

from app.producer import (DecisionEvent, ProducerError, append_event, build_package,
                          derive_policy_repr, input_digest, read_package,
                          write_package)
from app.verifier import VERIFIED, verify_package
from core import M0_AUDIT_SCHEMA, M0_PACKAGE_PROFILE
from core.canonical import canonical_bytes
from core.chain import entry_hash
from core.models import GENESIS_PREV_HASH, AuditEntry, Violation
from core.policy import policy_hash


class ProducerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def records(self, package: Path) -> list[dict]:
        text = (package / "evidence/audit.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]

    def manifest(self, package: Path) -> dict:
        return json.loads((package / "manifest.json").read_text(encoding="utf-8"))

    # ---- the loop itself ----------------------------------------------------

    def test_an_event_becomes_a_package_that_verifies(self):
        """EVENT -> PRODUCER -> PACKAGE -> VERIFIER -> VERIFIED."""
        package = produce_loan_package(self.root)
        result = verify_package(package)
        self.assertEqual(VERIFIED, result.status, f"reasons: {result.reasons}")
        self.assertEqual(len(LOAN_EVENTS), result.entries)
        self.assertEqual(PACKAGE_ID, result.package_id)

    def test_a_single_event_is_a_complete_package(self):
        """The smallest product loop: one decision, one package."""
        package = self.root / "one"
        write_package(package, build_package("one", LOAN_POLICY, LOAN_EVENTS[:1]))
        self.assertEqual(VERIFIED, verify_package(package).status)
        self.assertEqual(1, self.manifest(package)["entry_count"])

    def test_the_package_declares_the_m0_contract(self):
        package = produce_loan_package(self.root)
        manifest = self.manifest(package)
        self.assertEqual(M0_PACKAGE_PROFILE, manifest["profile"])
        self.assertEqual(M0_AUDIT_SCHEMA, manifest["audit_schema"])
        self.assertEqual("AURA-CANON/1", manifest["canonical_form"])
        self.assertEqual("SHA-256", manifest["digest"])

    def test_every_required_file_is_written(self):
        package = produce_loan_package(self.root)
        for required in ("manifest.json", "evidence/audit.jsonl",
                         "evidence/policy.json", "evidence/genesis.json"):
            with self.subTest(file=required):
                self.assertTrue((package / required).is_file())

    # ---- chain construction -------------------------------------------------

    def test_the_first_record_is_anchored_to_the_genesis_anchor(self):
        package = produce_loan_package(self.root)
        records = self.records(package)
        self.assertEqual(GENESIS_PREV_HASH, records[0]["prev_hash"])
        self.assertEqual(0, records[0]["seq"])

    def test_each_record_links_to_its_predecessor(self):
        """Genesis -> A -> B -> C, with prev_hash carrying the previous entry_hash."""
        records = self.records(produce_loan_package(self.root))
        self.assertEqual(3, len(records))
        for index, record in enumerate(records):
            with self.subTest(record=index):
                self.assertEqual(index, record["seq"])
                expected = (GENESIS_PREV_HASH if index == 0
                            else records[index - 1]["entry_hash"])
                self.assertEqual(expected, record["prev_hash"])

    def test_chain_position_is_assigned_by_the_producer_not_the_event(self):
        """An event carries no seq or prev_hash; placing a record is not its decision."""
        self.assertNotIn("seq", DecisionEvent.__dataclass_fields__)
        self.assertNotIn("prev_hash", DecisionEvent.__dataclass_fields__)

    def test_the_manifest_commits_to_the_chain_terminus(self):
        package = produce_loan_package(self.root)
        records = self.records(package)
        manifest = self.manifest(package)
        self.assertEqual(records[-1]["entry_hash"], manifest["chain_head"])
        self.assertEqual(len(records), manifest["entry_count"])

    def test_the_manifest_binds_the_bytes_of_every_declared_file(self):
        package = produce_loan_package(self.root)
        for relative, declared in self.manifest(package)["files"].items():
            with self.subTest(file=relative):
                actual = hashlib.sha256((package / relative).read_bytes()).hexdigest()
                self.assertEqual(declared, actual)

    # ---- no duplicated cryptography ----------------------------------------

    def test_entry_digests_come_from_the_accepted_chain_implementation(self):
        """Every digest the producer wrote is the one core.chain computes.

        This is the property that makes the producer an adapter rather than a second
        evidence specification: recomputed here through ``core.chain.entry_hash``
        from an ``AuditEntry`` rebuilt out of the record's own protected members.
        """
        records = self.records(produce_loan_package(self.root))
        for index, record in enumerate(records):
            with self.subTest(record=index):
                rebuilt = AuditEntry(
                    seq=record["seq"], request_id=record["request_id"],
                    timestamp=record["timestamp"], decision=record["decision"],
                    policy_hash=record["policy_hash"],
                    policy_repr=record["policy_repr"],
                    input_hash=record["input_hash"], prev_hash=record["prev_hash"],
                    violations=[Violation(v["rule"], v["action"], v["confidence"])
                                for v in record["violations"]],
                    metadata=dict(record["metadata"]),
                    shadow_hash=record.get("shadow_hash"),
                    schema=record["schema"],
                )
                self.assertEqual(entry_hash(rebuilt), record["entry_hash"])

    def test_the_digest_never_covers_itself(self):
        """entry_hash is SHA-256 over the canonical bytes that exclude entry_hash."""
        for record in self.records(produce_loan_package(self.root)):
            protected = {k: v for k, v in record.items() if k != "entry_hash"}
            self.assertEqual(
                hashlib.sha256(canonical_bytes(protected)).hexdigest(),
                record["entry_hash"],
            )

    def test_every_record_is_bound_to_the_policy_the_package_carries(self):
        package = produce_loan_package(self.root)
        policy = json.loads((package / "evidence/policy.json").read_text(encoding="utf-8"))
        expected = policy_hash(policy)
        self.assertEqual(policy_hash(LOAN_POLICY), expected)
        for record in self.records(package):
            self.assertEqual(expected, record["policy_hash"])

    def test_the_policy_document_travels_with_the_evidence(self):
        package = produce_loan_package(self.root)
        self.assertEqual(
            LOAN_POLICY,
            json.loads((package / "evidence/policy.json").read_text(encoding="utf-8")),
        )

    # ---- appending ----------------------------------------------------------

    def test_appending_extends_the_chain_across_invocations(self):
        """An application records one decision now and another later."""
        package = self.root / "incremental"
        write_package(package, build_package("incremental", LOAN_POLICY,
                                             LOAN_EVENTS[:1]))
        for event in LOAN_EVENTS[1:]:
            write_package(package, append_event(package, event))

        self.assertEqual(VERIFIED, verify_package(package).status)
        records = self.records(package)
        self.assertEqual([0, 1, 2], [r["seq"] for r in records])
        self.assertEqual(
            [event.request_id for event in LOAN_EVENTS],
            [r["request_id"] for r in records],
        )

    def test_appending_one_event_at_a_time_matches_producing_them_together(self):
        """Chain construction must not depend on how many invocations built it."""
        batched = produce_loan_package(self.root / "batched")
        incremental = self.root / "incremental" / PACKAGE_ID
        write_package(incremental, build_package(PACKAGE_ID, LOAN_POLICY,
                                                 LOAN_EVENTS[:1]))
        for event in LOAN_EVENTS[1:]:
            write_package(incremental, append_event(incremental, event))

        for relative in ("evidence/audit.jsonl", "manifest.json",
                         "evidence/policy.json", "evidence/genesis.json"):
            with self.subTest(file=relative):
                self.assertEqual((batched / relative).read_bytes(),
                                 (incremental / relative).read_bytes())

    def test_appending_under_a_different_policy_is_refused(self):
        """Every record in a package is bound to one policy document."""
        package = produce_loan_package(self.root)
        other = dict(LOAN_POLICY, version=3)
        with self.assertRaises(ProducerError) as caught:
            append_event(package, LOAN_EVENTS[0], policy_document=other)
        self.assertIn("policy", str(caught.exception))

    def test_reading_back_a_package_recovers_its_chain(self):
        package = produce_loan_package(self.root)
        state = read_package(package)
        self.assertEqual(PACKAGE_ID, state["package_id"])
        self.assertEqual(GENESIS_PREV_HASH, state["anchor"])
        self.assertEqual(LOAN_POLICY, state["policy"])
        self.assertEqual(3, len(state["records"]))

    # ---- refusals -----------------------------------------------------------

    def event(self, **overrides) -> DecisionEvent:
        base = {
            "request_id": "req-1", "timestamp": "2026-08-27T09:15:00Z",
            "decision": "ALLOW", "input_hash": "b" * 64,
        }
        base.update(overrides)
        return DecisionEvent(**base)

    def test_an_undefined_decision_is_refused_before_anything_is_written(self):
        target = self.root / "refused"
        with self.assertRaises(ProducerError):
            build_package("refused", LOAN_POLICY, [self.event(decision="WHATEVER")])
        self.assertFalse(target.exists())

    def test_a_malformed_timestamp_is_refused(self):
        with self.assertRaises(ProducerError):
            build_package("x", LOAN_POLICY,
                          [self.event(timestamp="2026-08-27 09:15:00")])

    def test_a_digest_outside_the_domain_is_refused(self):
        for bad in ("not-a-hash", "B" * 64, "b" * 63):
            with self.subTest(input_hash=bad), self.assertRaises(ProducerError):
                build_package("x", LOAN_POLICY, [self.event(input_hash=bad)])

    def test_an_empty_request_id_is_refused(self):
        with self.assertRaises(ProducerError):
            build_package("x", LOAN_POLICY, [self.event(request_id="")])

    def test_a_confidence_outside_the_scale_is_refused(self):
        with self.assertRaises(ProducerError):
            build_package("x", LOAN_POLICY, [self.event(
                violations=[{"rule": "R", "action": "BLOCK", "confidence": "1.5"}])])

    def test_an_unknown_event_field_is_refused_rather_than_dropped(self):
        """Silently dropping it would leave the application believing it was recorded."""
        with self.assertRaises(ProducerError) as caught:
            DecisionEvent.from_mapping({
                "request_id": "r", "timestamp": "2026-08-27T09:15:00Z",
                "decision": "ALLOW", "input_hash": "b" * 64, "actor": "agent-17",
            })
        self.assertIn("actor", str(caught.exception))

    def test_a_package_with_no_events_is_refused(self):
        with self.assertRaises(ProducerError):
            build_package("empty", LOAN_POLICY, [])

    def test_a_policy_document_with_no_canonical_form_is_refused(self):
        """AURA-CANON/1 forbids floating point; the policy is bound by canonical bytes."""
        with self.assertRaises(ProducerError):
            build_package("x", {"threshold": 0.43}, [self.event()])

    # ---- producer-side conveniences are not protocol -------------------------

    def test_the_input_reference_may_be_derived_from_a_local_input(self):
        payload = b'{"applicant":"A-1","dti_bp":4700}'
        self.assertEqual(hashlib.sha256(payload).hexdigest(), input_digest(payload))

        package = self.root / "derived"
        write_package(package, build_package("derived", LOAN_POLICY, [
            self.event(input_hash=input_digest(payload))]))
        self.assertEqual(VERIFIED, verify_package(package).status)

    def test_the_input_itself_never_enters_the_package(self):
        """M0 records a reference. The input is not evidence and is not carried."""
        payload = b"applicant-A-1-private-financials"
        package = self.root / "reference-only"
        write_package(package, build_package("reference-only", LOAN_POLICY, [
            self.event(input_hash=input_digest(payload))]))
        for path in package.rglob("*"):
            if path.is_file():
                self.assertNotIn(payload, path.read_bytes(),
                                 f"{path.name} carries the decision input itself")

    def test_the_policy_label_is_derived_only_when_stated_unambiguously(self):
        self.assertEqual("loan.underwriting/2", derive_policy_repr(LOAN_POLICY))
        self.assertEqual("", derive_policy_repr({"rules": []}))
        self.assertEqual("", derive_policy_repr({"policy_id": "x", "version": True}))


class SingleSourceOfTruthTest(unittest.TestCase):
    """The committed reference package is what the producer produces.

    If these drift, the repository holds two constructions of an Evidence Package and
    the fixtures stop being evidence about the product.
    """

    def test_the_reference_package_is_producer_generated(self):
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
        import build_m0_fixtures

        produced = build_m0_fixtures.build_package()
        for relative, data in produced.items():
            with self.subTest(file=relative):
                committed = (REFERENCE_PACKAGE / relative).read_bytes()
                self.assertEqual(committed, data,
                                 f"{relative} differs from what the producer builds")

    def test_the_committed_reference_package_still_verifies(self):
        self.assertEqual(VERIFIED, verify_package(REFERENCE_PACKAGE).status)

    def test_producing_the_scenario_reproduces_the_reference_package(self):
        """The product path and the accepted fixture are the same bytes.

        `expected/result.json` is excluded: it is non-normative fixture metadata that
        the fixture generator adds and the producer deliberately does not, because a
        package an application produces should carry evidence rather than an
        assertion about the verdict it expects.
        """
        with tempfile.TemporaryDirectory() as tmp:
            produced = produce_loan_package(Path(tmp))
            for relative in ("manifest.json", "evidence/audit.jsonl",
                             "evidence/policy.json", "evidence/genesis.json"):
                with self.subTest(file=relative):
                    self.assertEqual((REFERENCE_PACKAGE / relative).read_bytes(),
                                     (produced / relative).read_bytes())


if __name__ == "__main__":
    unittest.main()
