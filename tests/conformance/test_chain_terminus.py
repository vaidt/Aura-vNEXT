"""F-1 -- the chain terminus binding.

`prev_hash` binds each record to its predecessor, so the chain is bound only
*backwards*. The final record has nothing linking forward from it, and nothing
recorded how many records there should be. At 380e168 that meant the tail could be
rewritten, or records dropped from the end, while every remaining link stayed
consistent and the package still reached VERIFIED:

    tail record: decision DENY -> ALLOW, reseal that one record  -> VERIFIED
    delete the tail record                                       -> VERIFIED
    delete two records, keep genesis                             -> VERIFIED

Eight protected fields could be rewritten in the tail this way. A denied loan read
as allowed, and the package verified.

The manifest now declares the terminus:

    chain_head    the entry_hash of the final AuditEntry
    entry_count   the exact number of AuditEntry records

No new hashing domain: chain_head is the final record's own entry_hash, and the
AuditEntry canonical domain is untouched.

Classification follows the existing three-state contract. A malformed or missing
declaration is a manifest this verifier cannot interpret -- INVALID. A well-formed
declaration that does not match the evidence is a recognisable M0 package whose
evidence no longer matches what it committed to -- TAMPERED.

These tests repair the file digests after every mutation and never restate the
terminus, so a failure can only come from the terminus binding, never from a stale
outer checksum.
"""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _m0 import (copy_reference_package, read_records, refresh_manifest,
                 reseal_chain, write_records)

from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package
from core.canonical import canonical_bytes


def entry_hash_of(record: dict) -> str:
    protected = {k: v for k, v in record.items() if k != "entry_hash"}
    return hashlib.sha256(canonical_bytes(protected)).hexdigest()


class _TerminusCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self._n = 0

    def package(self, name: str = "") -> Path:
        self._n += 1
        return copy_reference_package(self.tmp / f"{name or 'pkg'}{self._n}")

    def reseal_record(self, package: Path, index: int) -> None:
        """Reseal one record correctly and repair the file digests -- nothing else.

        This is the attacker of the F-1 report: able to edit the evidence, recompute
        the record's own digest, and repair the manifest's file checksums.
        """
        records = read_records(package)
        records[index]["entry_hash"] = entry_hash_of(records[index])
        write_records(package, records)
        refresh_manifest(package)

    def manifest_of(self, package: Path) -> dict:
        return json.loads((package / "manifest.json").read_text(encoding="utf-8"))

    def write_manifest(self, package: Path, manifest: dict) -> None:
        (package / "manifest.json").write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    def assertTerminusRefused(self, package: Path, note: str):
        result = verify_package(package)
        self.assertEqual(
            TAMPERED, result.status,
            f"{note}: expected TAMPERED, got {result.status} ({result.reasons})",
        )
        self.assertTrue(result.reasons, f"{note}: TAMPERED with no stated reason")
        return result

    def assertCausedByTerminus(self, result, note: str):
        """The failure must come from the terminus, not an unrelated check."""
        self.assertTrue(
            any("chain_head" in r or "entry_count" in r for r in result.reasons),
            f"{note}: no terminus reason among {result.reasons}",
        )


class ManifestDeclaresTheTerminusTest(_TerminusCase):
    def test_the_reference_package_declares_a_correct_terminus(self):
        package = self.package("reference")
        manifest = self.manifest_of(package)
        records = read_records(package)

        self.assertEqual(len(records), manifest["entry_count"])
        self.assertEqual(records[-1]["entry_hash"], manifest["chain_head"])
        self.assertEqual(VERIFIED, verify_package(package).status)

    def test_chain_head_is_the_final_entry_hash_not_a_file_digest(self):
        """No new hashing domain: it is the record's own entry_hash."""
        package = self.package("domain")
        records = read_records(package)
        manifest = self.manifest_of(package)

        self.assertEqual(entry_hash_of(records[-1]), manifest["chain_head"])
        file_digest = hashlib.sha256(
            (package / "evidence/audit.jsonl").read_bytes()
        ).hexdigest()
        self.assertNotEqual(file_digest, manifest["chain_head"])


class TailForgeryTest(_TerminusCase):
    """Attack 1: rewrite the final record and reseal it correctly."""

    def test_tail_decision_mutation_is_tampered(self):
        package = self.package("decision")
        records = read_records(package)
        self.assertEqual("DENY", records[2]["decision"], "precondition: C is DENY")

        records[2]["decision"] = "ALLOW"
        write_records(package, records)
        self.reseal_record(package, 2)

        # Precondition: the forged record really is correctly sealed, and the file
        # digests really do match -- so nothing but the terminus can reject it.
        records = read_records(package)
        self.assertEqual(entry_hash_of(records[2]), records[2]["entry_hash"])
        manifest = self.manifest_of(package)
        for relative, expected in manifest["files"].items():
            self.assertEqual(
                expected,
                hashlib.sha256((package / relative).read_bytes()).hexdigest(),
            )

        result = self.assertTerminusRefused(package, "tail decision DENY->ALLOW")
        self.assertCausedByTerminus(result, "tail decision")

    def test_every_tail_field_that_previously_verified_is_now_tampered(self):
        """The eight fields the F-1 report measured reaching VERIFIED."""
        for field, value in (("request_id", "forged"),
                             ("timestamp", "2026-08-27T09:16:59Z"),
                             ("decision", "ALLOW"),
                             ("policy_repr", "loan.underwriting/9"),
                             ("input_hash", "e" * 64),
                             ("violations", []),
                             ("metadata", {"actor": "forged"}),
                             ("shadow_hash", "b" * 64)):
            with self.subTest(field=field):
                package = self.package(f"tail-{field}")
                records = read_records(package)
                records[2][field] = value
                write_records(package, records)
                self.reseal_record(package, 2)
                result = self.assertTerminusRefused(package, f"tail {field}")
                self.assertCausedByTerminus(result, f"tail {field}")

    def test_tail_policy_hash_mutation_is_tampered(self):
        package = self.package("tail-policy")
        records = read_records(package)
        records[2]["policy_hash"] = "f" * 64
        write_records(package, records)
        self.reseal_record(package, 2)
        self.assertTerminusRefused(package, "tail policy_hash")


class TailTruncationTest(_TerminusCase):
    """Attack 2: drop records from the end."""

    def test_deleting_the_tail_record_is_tampered(self):
        package = self.package("truncate")
        records = read_records(package)
        del records[2]
        write_records(package, records)
        refresh_manifest(package)

        result = self.assertTerminusRefused(package, "tail deleted")
        self.assertCausedByTerminus(result, "tail deleted")

    def test_deleting_two_records_is_tampered(self):
        package = self.package("truncate2")
        records = read_records(package)
        del records[2], records[1]
        write_records(package, records)
        refresh_manifest(package)
        self.assertTerminusRefused(package, "two records deleted")

    def test_truncation_is_refused_even_when_the_remaining_chain_is_consistent(self):
        """Truncation leaves every surviving link intact; only the terminus differs."""
        package = self.package("truncate3")
        records = read_records(package)
        del records[2]
        write_records(package, records)
        refresh_manifest(package)

        survivors = read_records(package)
        self.assertEqual(survivors[0]["entry_hash"], survivors[1]["prev_hash"],
                         "precondition: the surviving links must still be consistent")
        for record in survivors:
            self.assertEqual(entry_hash_of(record), record["entry_hash"])

        self.assertTerminusRefused(package, "consistent truncation")


class TailAppendTest(_TerminusCase):
    """Attack 3: append a correctly linked, correctly sealed record."""

    def test_appending_a_correctly_linked_record_is_tampered(self):
        package = self.package("append")
        records = read_records(package)
        forged = json.loads(json.dumps(records[2]))
        forged["seq"] = 3
        forged["request_id"] = "loan-001-appended"
        forged["prev_hash"] = records[2]["entry_hash"]
        forged["entry_hash"] = entry_hash_of(forged)
        records.append(forged)
        write_records(package, records)
        refresh_manifest(package)

        # Precondition: the appended record links and seals correctly, so only the
        # terminus stands between it and VERIFIED.
        appended = read_records(package)
        self.assertEqual(appended[2]["entry_hash"], appended[3]["prev_hash"])
        self.assertEqual(entry_hash_of(appended[3]), appended[3]["entry_hash"])

        result = self.assertTerminusRefused(package, "appended record")
        self.assertCausedByTerminus(result, "appended record")


class DeclarationTamperingTest(_TerminusCase):
    """A well-formed declaration that disagrees with the evidence."""

    def test_wrong_chain_head_is_tampered(self):
        package = self.package("wrong-head")
        manifest = self.manifest_of(package)
        manifest["chain_head"] = "f" * 64
        self.write_manifest(package, manifest)
        result = self.assertTerminusRefused(package, "wrong chain_head")
        self.assertTrue(any("chain_head" in r for r in result.reasons), result.reasons)

    def test_chain_head_naming_a_non_final_record_is_tampered(self):
        """Pointing at an interior record would let the tail be dropped."""
        package = self.package("interior-head")
        records = read_records(package)
        manifest = self.manifest_of(package)
        manifest["chain_head"] = records[1]["entry_hash"]
        self.write_manifest(package, manifest)
        self.assertTerminusRefused(package, "chain_head naming record 1")

    def test_wrong_entry_count_is_tampered(self):
        for value in (1, 2, 4, 99):
            with self.subTest(entry_count=value):
                package = self.package(f"count{value}")
                manifest = self.manifest_of(package)
                manifest["entry_count"] = value
                self.write_manifest(package, manifest)
                result = self.assertTerminusRefused(package, f"entry_count {value}")
                self.assertTrue(any("entry_count" in r for r in result.reasons),
                                result.reasons)


class MalformedDeclarationTest(_TerminusCase):
    """A declaration this verifier cannot interpret is INVALID, not TAMPERED."""

    def assertInvalid(self, package: Path, note: str):
        result = verify_package(package)
        self.assertEqual(
            INVALID, result.status,
            f"{note}: expected INVALID, got {result.status} ({result.reasons})",
        )

    def test_missing_declarations_are_invalid(self):
        for key in ("chain_head", "entry_count"):
            with self.subTest(missing=key):
                package = self.package(f"missing-{key}")
                manifest = self.manifest_of(package)
                del manifest[key]
                self.write_manifest(package, manifest)
                self.assertInvalid(package, f"missing {key}")

    def test_malformed_chain_head_is_invalid(self):
        for value in ("xyz", "", "A" * 64, "a" * 63, 12345, None, ["a" * 64]):
            with self.subTest(chain_head=value):
                package = self.package("bad-head")
                manifest = self.manifest_of(package)
                manifest["chain_head"] = value
                self.write_manifest(package, manifest)
                self.assertInvalid(package, f"chain_head {value!r}")

    def test_malformed_entry_count_is_invalid(self):
        for value in ("3", 3.0, None, True, [3], -1, 0):
            with self.subTest(entry_count=value):
                package = self.package("bad-count")
                manifest = self.manifest_of(package)
                manifest["entry_count"] = value
                self.write_manifest(package, manifest)
                self.assertInvalid(package, f"entry_count {value!r}")


class ExistingClassificationsPreservedTest(_TerminusCase):
    """The terminus binding must not disturb what already worked."""

    def test_reference_package_still_verifies(self):
        result = verify_package(self.package("ok"))
        self.assertEqual(VERIFIED, result.status, result.reasons)
        self.assertEqual(3, result.entries)

    def test_interior_mutation_is_still_tampered(self):
        package = self.package("interior")
        records = read_records(package)
        records[0]["decision"] = "DENY"
        write_records(package, records)
        refresh_manifest(package)
        self.assertEqual(TAMPERED, verify_package(package).status)

    def test_malformed_package_is_still_invalid(self):
        package = self.package("malformed")
        (package / "manifest.json").write_text("{ not json", encoding="utf-8")
        self.assertEqual(INVALID, verify_package(package).status)

    def test_semantically_invalid_record_is_still_invalid(self):
        package = self.package("semantic")
        records = read_records(package)
        records[0]["decision"] = "WHATEVER"
        write_records(package, records)
        reseal_chain(package)
        self.assertEqual(INVALID, verify_package(package).status)

    def test_all_three_states_remain_reachable(self):
        verified = self.package("s-verified")

        tampered = self.package("s-tampered")
        records = read_records(tampered)
        records[2]["decision"] = "ALLOW"
        write_records(tampered, records)
        self.reseal_record(tampered, 2)

        invalid = self.package("s-invalid")
        (invalid / "manifest.json").write_text("{", encoding="utf-8")

        self.assertEqual(
            {VERIFIED, TAMPERED, INVALID},
            {verify_package(p).status for p in (verified, tampered, invalid)},
        )

    def test_a_full_rewrite_still_verifies_and_that_limit_is_recorded(self):
        """The remaining, documented limitation.

        The terminus raises the cost of a forgery from one record to the whole chain
        plus the manifest. It does not eliminate it: the manifest is unsigned, so a
        party willing to restate the terminus too still produces a self-consistent
        package. VERIFIED means integrity, never authorship.
        """
        package = self.package("full-rewrite")
        records = read_records(package)
        records[2]["decision"] = "ALLOW"
        write_records(package, records)
        reseal_chain(package)
        self.assertEqual(VERIFIED, verify_package(package).status)


if __name__ == "__main__":
    unittest.main()
