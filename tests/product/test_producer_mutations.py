"""Adversarial tests against a package the producer actually built.

`tests/mutation/` already covers the protected domain element by element, against the
committed reference package. This suite does not repeat that work. It asks a
different question:

    does a package produced by `aura record` -- rather than written by hand --
    hold up under the same attacks?

The mutation classes here are the ones the product loop makes claims about: the
decision, the policy binding, the input reference, the chain, its two ends, the
manifest, and a package corrupted beyond reading. Each starts from a freshly produced
package, mutates one thing, and asserts the external classification.

Every mutation refreshes the manifest digests afterwards (`_m0.refresh_manifest`).
Without that the outer checksum would catch everything and the canonical binding
would never be exercised; refreshing models the stronger attacker, who edits the
evidence and repairs the obvious checksum.
"""

import json
import tempfile
import unittest
from pathlib import Path

from _m0 import read_records, refresh_manifest, reseal_chain, write_records
from _product import produce_loan_package

from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package


class ProducerPackageMutationTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.package = produce_loan_package(Path(self._tmp.name))

    # ---- harness ------------------------------------------------------------

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

    def assertInvalid(self, note: str):
        result = verify_package(self.package)
        self.assertEqual(
            INVALID, result.status,
            f"{note}: expected INVALID, got {result.status} (reasons: {result.reasons})",
        )

    def records(self) -> list[dict]:
        return read_records(self.package)

    def rewrite(self, records: list[dict]) -> None:
        write_records(self.package, records)
        refresh_manifest(self.package)

    def manifest(self) -> dict:
        return json.loads((self.package / "manifest.json").read_text(encoding="utf-8"))

    def rewrite_manifest(self, **changes) -> None:
        manifest = self.manifest()
        manifest.update(changes)
        (self.package / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    # ---- baseline -----------------------------------------------------------

    def test_the_produced_package_is_the_baseline(self):
        """If this fails, every assertion below proves nothing."""
        self.assertVerified()

    def test_refreshing_the_manifest_alone_does_not_change_the_verdict(self):
        """The harness must not be what causes the failures it reports."""
        refresh_manifest(self.package)
        self.assertVerified()

    # ---- the mutation matrix ------------------------------------------------

    def test_decision_mutation(self):
        """The claim the product exists to protect: DENY cannot become ALLOW."""
        records = self.records()
        self.assertEqual("DENY", records[-1]["decision"])
        records[-1]["decision"] = "ALLOW"
        self.rewrite(records)
        self.assertTampered("decision DENY -> ALLOW")

    def test_policy_reference_mutation(self):
        """A record pointed at a different policy than the one it was taken under."""
        records = self.records()
        records[0]["policy_hash"] = "d" * 64
        self.rewrite(records)
        self.assertTampered("policy_hash replaced")

    def test_policy_document_mutation(self):
        """Editing the carried policy breaks the binding every record declares."""
        path = self.package / "evidence/policy.json"
        policy = json.loads(path.read_text(encoding="utf-8"))
        policy["rules"][0]["threshold_bp"] = 9900
        path.write_text(json.dumps(policy, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
        refresh_manifest(self.package)
        self.assertTampered("policy document edited")

    def test_policy_label_mutation(self):
        """policy_repr has no value constraint, so it stays a protected value."""
        records = self.records()
        records[0]["policy_repr"] = "loan.underwriting/3"
        self.rewrite(records)
        self.assertTampered("policy_repr rewritten")

    def test_input_reference_mutation(self):
        records = self.records()
        records[1]["input_hash"] = "d" * 64
        self.rewrite(records)
        self.assertTampered("input_hash replaced")

    def test_chain_link_mutation(self):
        """Relinking a record to a different predecessor."""
        records = self.records()
        records[2]["prev_hash"] = records[0]["entry_hash"]
        self.rewrite(records)
        self.assertTampered("prev_hash relinked")

    def test_chain_reordering(self):
        records = self.records()
        records[1], records[2] = records[2], records[1]
        self.rewrite(records)
        self.assertTampered("records reordered")

    def test_interior_record_deletion(self):
        records = self.records()
        del records[1]
        self.rewrite(records)
        self.assertTampered("interior record removed")

    def test_tail_deletion(self):
        """Dropping the last record leaves every remaining link consistent.

        Only the manifest's declared terminus catches this, which is why the terminus
        is part of what the producer commits to.
        """
        records = self.records()
        del records[-1]
        self.rewrite(records)
        self.assertTampered("tail record dropped")

    def test_tail_deletion_survives_a_full_reseal_of_what_remains(self):
        """A stronger attacker: drop the tail, then relink and reseal the remainder.

        `reseal_chain` also rewrites the manifest terminus, so what is left is a
        self-consistent shorter chain. It is still refused, because the package
        declares three entries.
        """
        records = self.records()
        head = self.manifest()["chain_head"]
        count = self.manifest()["entry_count"]
        del records[-1]
        write_records(self.package, records)
        reseal_chain(self.package)
        self.rewrite_manifest(chain_head=head, entry_count=count)
        self.assertTampered("tail dropped and the remainder resealed")

    def test_tail_append(self):
        """A record added after the committed terminus, correctly linked and sealed."""
        import hashlib

        from core.canonical import canonical_bytes

        records = self.records()
        forged = dict(records[-1])
        forged["seq"] = len(records)
        forged["request_id"] = "loan-001-appended"
        forged["decision"] = "ALLOW"
        forged["prev_hash"] = records[-1]["entry_hash"]
        protected = {k: v for k, v in forged.items() if k != "entry_hash"}
        forged["entry_hash"] = hashlib.sha256(canonical_bytes(protected)).hexdigest()
        records.append(forged)
        self.rewrite(records)
        self.assertTampered("record appended past the declared terminus")

    def test_manifest_terminus_mutation(self):
        """Rewriting the declared chain head to something the evidence does not carry."""
        self.rewrite_manifest(chain_head="d" * 64)
        self.assertTampered("chain_head rewritten")

    def test_manifest_entry_count_mutation(self):
        self.rewrite_manifest(entry_count=2)
        self.assertTampered("entry_count rewritten")

    def test_manifest_digest_left_stale(self):
        """The outer checksum on its own still catches an edit that ignores it."""
        records = self.records()
        records[0]["decision"] = "DENY"
        write_records(self.package, records)  # deliberately not refreshed
        self.assertTampered("evidence edited, manifest digest left stale")

    def test_genesis_anchor_mutation(self):
        path = self.package / "evidence/genesis.json"
        genesis = json.loads(path.read_text(encoding="utf-8"))
        genesis["prev_hash"] = "d" * 64
        path.write_text(json.dumps(genesis, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
        refresh_manifest(self.package)
        self.assertTampered("chain anchor moved")

    # ---- corruption is a different answer -----------------------------------

    def test_package_corruption_is_invalid(self):
        (self.package / "evidence/audit.jsonl").write_bytes(b"\x00\x01 not jsonl\n")
        refresh_manifest(self.package)
        self.assertInvalid("audit chain corrupted beyond reading")

    def test_a_missing_manifest_is_invalid(self):
        (self.package / "manifest.json").unlink()
        self.assertInvalid("manifest removed")

    def test_a_missing_required_file_is_invalid(self):
        (self.package / "evidence/policy.json").unlink()
        self.assertInvalid("policy document removed")

    def test_an_undefined_decision_value_is_invalid_not_tampered(self):
        """A resealed record carrying a decision M0 does not define is unreadable.

        It is refused before it is hashed, so it cannot present as intact evidence for
        an outcome the contract never defined.
        """
        records = self.records()
        records[-1]["decision"] = "WHATEVER"
        write_records(self.package, records)
        reseal_chain(self.package)
        self.assertInvalid("decision outside the closed vocabulary")


class MutationMatrixCoverageTest(unittest.TestCase):
    """Every mutation class this suite claims to cover must have a test.

    Stated as an assertion rather than a comment, so removing a test is a failure
    rather than a silent narrowing of the claim.
    """

    REQUIRED = {
        "decision": "test_decision_mutation",
        "policy": "test_policy_document_mutation",
        "input reference": "test_input_reference_mutation",
        "chain": "test_chain_link_mutation",
        "tail deletion": "test_tail_deletion",
        "tail append": "test_tail_append",
        "manifest": "test_manifest_terminus_mutation",
        "corruption": "test_package_corruption_is_invalid",
    }

    def test_every_named_mutation_class_is_covered(self):
        for element, name in self.REQUIRED.items():
            with self.subTest(mutation=element):
                self.assertTrue(
                    hasattr(ProducerPackageMutationTest, name),
                    f"no test covers the {element} mutation",
                )


if __name__ == "__main__":
    unittest.main()
