"""Evidence Package trust-boundary enforcement.

The M0 claim is that a verifier operates from the Evidence Package itself and
depends on no hidden state outside it. The manifest is untrusted input -- it
travels with the evidence -- so a manifest-declared path is an instruction from
the package about which files to read. If such a path can escape the package
root, the claim is false: the verifier reads outside the trust boundary.

Reproduced against b4dd3ff, before the fix: parent traversal, nested traversal,
absolute path, and symlink escape all returned **VERIFIED** while the verifier
digested a file outside the package. ``Path(root) / "../outside"`` stays lexically
inside but resolves out, and ``Path(root) / "/etc/hostname"`` discards the root
entirely.

These tests assert the security property, not merely that verification failed:
every boundary violation must classify as INVALID specifically. A package that
instructs the verifier to read outside itself is not a recognisable M0 package
whose evidence fails integrity -- it is not an M0 package at all.
"""

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from _m0 import copy_reference_package

from app.verifier import INVALID, TAMPERED, VERIFIED, verify_package


class _BoundaryCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

        # A file that lives outside every package built in this test.
        self.outside = self.tmp / "outside.txt"
        self.outside.write_text("SECRET DATA OUTSIDE THE PACKAGE\n", encoding="utf-8")
        self.outside_digest = hashlib.sha256(self.outside.read_bytes()).hexdigest()

    def package_declaring(self, name: str, path: str, digest: str) -> Path:
        """Build a package whose manifest declares ``path`` with a correct digest.

        The digest is correct on purpose. If it were wrong, the package would fail
        on the digest comparison and the test would prove nothing about the
        boundary -- the point is that the read must never happen at all.
        """
        package = copy_reference_package(self.tmp / name)
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"][path] = digest
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        return package

    def assertBoundaryRefused(self, package: Path, note: str):
        result = verify_package(package)
        self.assertEqual(
            INVALID, result.status,
            f"{note}: expected INVALID, got {result.status} ({result.reasons})",
        )
        self.assertNotEqual(
            TAMPERED, result.status,
            f"{note}: a path outside the package is an invalid package, not tampering",
        )
        self.assertTrue(result.reasons, f"{note}: INVALID with no stated reason")
        return result


class ParentTraversalTest(_BoundaryCase):
    def test_parent_traversal_is_invalid(self):
        package = self.package_declaring(
            "parent", "../outside.txt", self.outside_digest
        )
        self.assertBoundaryRefused(package, "../outside.txt")

    def test_deep_parent_traversal_is_invalid(self):
        package = self.package_declaring(
            "deep", "../../outside.txt", self.outside_digest
        )
        self.assertBoundaryRefused(package, "../../outside.txt")

    def test_nested_traversal_is_invalid(self):
        for index, path in enumerate((
            "evidence/../outside.txt",
            "evidence/../../outside.txt",
            "evidence/nested/../../../outside.txt",
        )):
            with self.subTest(path=path):
                package = self.package_declaring(
                    f"nested{index}", path, self.outside_digest
                )
                self.assertBoundaryRefused(package, path)

    def test_non_canonical_spellings_are_invalid(self):
        """PurePosixPath drops these silently, so a component scan cannot see them.

        Refused rather than normalised: the manifest is a digest map keyed by
        these strings, so two spellings of one file would be two entries able to
        declare two different digests for the same bytes.
        """
        for index, path in enumerate((
            "./evidence/policy.json",
            "evidence/./policy.json",
            "evidence//policy.json",
            "evidence/policy.json/",
        )):
            with self.subTest(path=path):
                package = self.package_declaring(
                    f"noncanon{index}", path, self.outside_digest
                )
                self.assertBoundaryRefused(package, path)

    def test_a_file_cannot_be_declared_twice_under_two_spellings(self):
        """The concrete hazard the canonical-form rule closes."""
        package = copy_reference_package(self.tmp / "twospellings")
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["./evidence/policy.json"] = "f" * 64
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        self.assertBoundaryRefused(package, "same file under two spellings")

    def test_traversal_that_lands_back_inside_is_still_invalid(self):
        """Refused on spelling, not only on where it happens to land.

        'evidence/../evidence/policy.json' resolves inside the package, so a
        containment-only check would allow it. The declaration is still not a
        plain package path, and accepting it would mean the two checks disagree
        about what a package path is.
        """
        package = copy_reference_package(self.tmp / "roundtrip")
        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = manifest["files"].pop("evidence/policy.json")
        manifest["files"]["evidence/../evidence/policy.json"] = digest
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        self.assertBoundaryRefused(package, "evidence/../evidence/policy.json")


class AbsolutePathTest(_BoundaryCase):
    def test_absolute_path_is_invalid(self):
        """`Path(root) / "/etc/hostname"` is `/etc/hostname`: the root is discarded."""
        absolute = str(self.outside)
        package = self.package_declaring("abs", absolute, self.outside_digest)
        self.assertBoundaryRefused(package, absolute)

    def test_absolute_system_path_is_invalid(self):
        target = "/etc/hostname"
        digest = (hashlib.sha256(Path(target).read_bytes()).hexdigest()
                  if Path(target).is_file() else "0" * 64)
        package = self.package_declaring("abs-sys", target, digest)
        self.assertBoundaryRefused(package, target)

    def test_root_itself_is_invalid(self):
        package = self.package_declaring("root", "/", "0" * 64)
        self.assertBoundaryRefused(package, "/")

    def test_empty_and_non_string_paths_are_invalid(self):
        for index, path in enumerate(("", ".", "..")):
            with self.subTest(path=path):
                package = self.package_declaring(f"empty{index}", path, "0" * 64)
                self.assertBoundaryRefused(package, repr(path))

    def test_backslash_separator_is_invalid(self):
        """A backslash is a separator on some platforms; package paths are POSIX."""
        package = self.package_declaring(
            "backslash", "..\\outside.txt", self.outside_digest
        )
        self.assertBoundaryRefused(package, "..\\outside.txt")


@unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlinks")
class SymlinkEscapeTest(_BoundaryCase):
    """A package-local symlink whose target resolves outside the package."""

    def test_symlink_to_a_file_outside_the_package_is_invalid(self):
        package = copy_reference_package(self.tmp / "symlink")
        (package / "evidence" / "escape").symlink_to(self.outside)

        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["evidence/escape"] = self.outside_digest
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

        # Precondition: the link really does reach the outside file, so the test
        # is exercising an escape rather than a broken link.
        self.assertTrue((package / "evidence" / "escape").is_file())
        self.assertEqual(
            self.outside.read_bytes(),
            (package / "evidence" / "escape").read_bytes(),
        )

        self.assertBoundaryRefused(package, "symlink to outside")

    def test_symlink_to_a_directory_outside_the_package_is_invalid(self):
        outside_dir = self.tmp / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "secret.txt").write_text("x", encoding="utf-8")

        package = copy_reference_package(self.tmp / "symlink-dir")
        (package / "evidence" / "linked").symlink_to(outside_dir, target_is_directory=True)

        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["evidence/linked/secret.txt"] = hashlib.sha256(b"x").hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        self.assertBoundaryRefused(package, "symlink to outside directory")

    def test_a_symlink_staying_inside_the_package_is_not_an_escape(self):
        """Containment is the rule, not a blanket ban on symlinks.

        A link that resolves inside the package has not left the trust boundary,
        so it must not be refused -- otherwise the check would be testing for
        symlinks rather than for escape.
        """
        package = copy_reference_package(self.tmp / "symlink-inside")
        (package / "evidence" / "alias.json").symlink_to(package / "evidence/policy.json")

        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["evidence/alias.json"] = manifest["files"]["evidence/policy.json"]
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        self.assertEqual(VERIFIED, verify_package(package).status)


class LegitimateInternalPathTest(_BoundaryCase):
    """The boundary check must not break packages that stay inside it."""

    def test_the_reference_package_still_verifies(self):
        package = copy_reference_package(self.tmp / "reference")
        result = verify_package(package)
        self.assertEqual(VERIFIED, result.status, result.reasons)
        self.assertEqual(3, result.entries)

    def test_an_additional_declared_file_inside_the_package_verifies(self):
        """A legitimate nested path is accepted and is actually digested."""
        package = copy_reference_package(self.tmp / "extra")
        extra = package / "evidence" / "nested" / "note.txt"
        extra.parent.mkdir(parents=True)
        extra.write_text("inside the package\n", encoding="utf-8")

        manifest_path = package / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["files"]["evidence/nested/note.txt"] = hashlib.sha256(
            extra.read_bytes()
        ).hexdigest()
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        self.assertEqual(VERIFIED, verify_package(package).status)

        # And it is genuinely checked, not merely tolerated.
        extra.write_text("altered\n", encoding="utf-8")
        self.assertEqual(TAMPERED, verify_package(package).status)

    def test_a_package_reached_through_a_symlinked_root_verifies(self):
        """The boundary is the resolved root, so a symlinked package still works."""
        package = copy_reference_package(self.tmp / "real")
        link = self.tmp / "linked-package"
        link.symlink_to(package, target_is_directory=True)
        self.assertEqual(VERIFIED, verify_package(link).status)


class BoundaryPrecedesReadingTest(_BoundaryCase):
    """The refusal must happen before the outside file is read, not after."""

    def test_an_escaping_path_is_refused_even_when_the_target_does_not_exist(self):
        """No filesystem access is needed to refuse a traversal declaration."""
        package = self.package_declaring(
            "absent", "../does-not-exist.txt", "0" * 64
        )
        self.assertBoundaryRefused(package, "non-existent outside target")

    def test_an_escaping_path_is_refused_even_with_a_wrong_digest(self):
        """The verdict must be INVALID on the boundary, not TAMPERED on the digest.

        With a deliberately wrong digest, a verifier that read the file first
        would report TAMPERED -- and would already have read outside the package.
        """
        package = self.package_declaring("wrong", "../outside.txt", "f" * 64)
        self.assertBoundaryRefused(package, "escape with a wrong digest")

    def test_the_three_states_remain_distinct_under_boundary_enforcement(self):
        verified = copy_reference_package(self.tmp / "state-verified")

        tampered = copy_reference_package(self.tmp / "state-tampered")
        policy = tampered / "evidence/policy.json"
        policy.write_text(policy.read_text(encoding="utf-8") + " ", encoding="utf-8")

        invalid = self.package_declaring("state-invalid", "../outside.txt",
                                         self.outside_digest)

        self.assertEqual(
            {VERIFIED, TAMPERED, INVALID},
            {verify_package(p).status for p in (verified, tampered, invalid)},
        )


if __name__ == "__main__":
    unittest.main()
