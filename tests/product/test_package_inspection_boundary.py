"""`aura package` and the package boundary: inspection stays inside the package.

`aura verify` already refuses a manifest-declared path that escapes the package
root, and `tests/conformance/test_package_boundary.py` holds it to that. This
suite covers the other public command that follows the same declarations:
`aura package`.

The manifest is untrusted input -- it travels with the evidence and is written by
whoever produced or last touched the package -- so a declared path is an
instruction from the package about which file to look at. Joining it to the
package root is not containment: '../outside' stays lexically inside and resolves
out, an absolute path discards the root entirely, and a package-local symlink can
point anywhere. Before the fix, `aura package` reported such a path as a carried
file, `present: true`, at exit 0: the package chose a file outside itself and the
inspection command confirmed it was there.

Two properties are asserted here, and they are different:

  * the escape is REFUSED. Not VERIFIED, not TAMPERED, not INVALID -- `package`
    describes and never judges, so a boundary failure leaves by the same exit
    status as every other thing this command declines to do (65), and emits no
    description at all;
  * the outside file is never read. A refusal that happened after the read would
    satisfy the first property and none of the point of it.

On the second: resolving a package-local symlink necessarily lstats what it
points at -- that is how a link that leaves the package is caught, and it is the
containment check itself, not an inspection. What must never happen is the file
being opened, its bytes read, or its existence reported in a description. That is
what the recorder below pins.
"""

import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from _product import produce_loan_package, run_aura

import app.aura
from app.aura import EXIT_OK, EXIT_REFUSED

VERDICT_STATUSES = (0, 2, 3)   # VERIFIED, TAMPERED, INVALID -- `verify`'s alone

# Contents an inspection would have to have read to reproduce. Deliberately not a
# path, so finding it in the output cannot be confused with the command naming the
# declaration it refused.
SENTINEL = "AURA-TEST-SENTINEL-OUTSIDE-THE-PACKAGE"


class _InspectionBoundaryCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

        # A file that lives outside every package built in this test.
        self.outside = self.root / "outside.json"
        self.outside.write_text(
            json.dumps({"note": SENTINEL}, indent=2) + "\n", encoding="utf-8"
        )
        self.outside_digest = hashlib.sha256(self.outside.read_bytes()).hexdigest()

        self.package = produce_loan_package(self.root)
        self.manifest_path = self.package / "manifest.json"
        self.pristine_manifest = self.manifest_path.read_text(encoding="utf-8")

    def declare(self, path: str, digest: str | None = None) -> None:
        """Declare ``path`` in the manifest's file set, with a correct digest.

        The digest is correct on purpose: a wrong one would let the command fail
        for a reason that has nothing to do with the boundary. The manifest is
        rewritten from the pristine one each time, so a subTest never inherits the
        declaration made by the one before it.
        """
        manifest = json.loads(self.pristine_manifest)
        manifest["files"][path] = digest if digest is not None else self.outside_digest
        self.manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )

    def assertInspectionRefused(self, note: str):
        """`aura package` refuses, describes nothing, and returns no verdict."""
        for extra in ((), ("--json",)):
            with self.subTest(mode="json" if extra else "text"):
                completed = run_aura("package", str(self.package), *extra)
                self.assertEqual(
                    EXIT_REFUSED, completed.returncode,
                    f"{note}: expected a refusal (65), got {completed.returncode} "
                    f"({completed.stdout}{completed.stderr})",
                )
                self.assertNotIn(
                    completed.returncode, VERDICT_STATUSES,
                    f"{note}: inspection must not return a verdict status",
                )
                self.assertEqual(
                    "", completed.stdout,
                    f"{note}: a refused package must not be described",
                )
                self.assertNotIn(SENTINEL, completed.stdout + completed.stderr,
                                 f"{note}: the outside file's contents reached the output")
                self.assertIn("manifest.json", completed.stderr,
                              f"{note}: the refusal must name the declaration it refused")
        return completed


class TraversalTest(_InspectionBoundaryCase):
    def test_parent_traversal_is_refused(self):
        self.declare("../outside.json")
        self.assertInspectionRefused("../outside.json")

    def test_nested_traversal_is_refused(self):
        for path in ("evidence/../../outside.json",
                     "evidence/../outside.json",
                     "evidence/nested/../../../outside.json"):
            with self.subTest(path=path):
                self.declare(path)
                self.assertInspectionRefused(path)

    def test_traversal_landing_back_inside_is_still_refused(self):
        """Refused on spelling, as the verifier refuses it.

        'evidence/../evidence/policy.json' resolves inside the package, so a
        containment-only check would allow it here while the verifier refused it.
        The two commands must not disagree about what a package path is.
        """
        self.declare("evidence/../evidence/policy.json", "0" * 64)
        self.assertInspectionRefused("evidence/../evidence/policy.json")

    def test_traversal_is_refused_even_when_the_target_does_not_exist(self):
        """No filesystem access is needed to refuse a traversal declaration."""
        self.declare("../does-not-exist.json", "0" * 64)
        self.assertInspectionRefused("non-existent outside target")


class AbsolutePathTest(_InspectionBoundaryCase):
    def test_absolute_path_is_refused(self):
        """`Path(root) / "/abs/path"` is `/abs/path`: the root is discarded."""
        self.declare(str(self.outside))
        self.assertInspectionRefused(str(self.outside))

    def test_absolute_system_path_is_refused(self):
        target = "/etc/hostname"
        digest = (hashlib.sha256(Path(target).read_bytes()).hexdigest()
                  if Path(target).is_file() else "0" * 64)
        self.declare(target, digest)
        self.assertInspectionRefused(target)

    def test_the_filesystem_root_is_refused(self):
        self.declare("/", "0" * 64)
        self.assertInspectionRefused("/")

    def test_empty_and_dot_paths_are_refused(self):
        for path in ("", ".", ".."):
            with self.subTest(path=path):
                self.declare(path, "0" * 64)
                self.assertInspectionRefused(repr(path))


class BackslashPathTest(_InspectionBoundaryCase):
    def test_backslash_separator_is_refused(self):
        """A backslash is a separator on some platforms; package paths are POSIX."""
        self.declare("..\\outside.json")
        self.assertInspectionRefused("..\\outside.json")

    def test_backslash_inside_the_package_is_refused(self):
        self.declare("evidence\\policy.json", "0" * 64)
        self.assertInspectionRefused("evidence\\policy.json")


class AlternateSpellingTest(_InspectionBoundaryCase):
    def test_non_canonical_spellings_are_refused(self):
        """PurePosixPath drops these silently, so a component scan cannot see them.

        They matter because the manifest is a digest map keyed by these strings:
        two spellings of one file would be two entries able to declare two
        different digests for the same bytes.
        """
        for path in ("./evidence/policy.json",
                     "evidence/./policy.json",
                     "evidence//policy.json",
                     "evidence/policy.json/"):
            with self.subTest(path=path):
                self.declare(path, "0" * 64)
                self.assertInspectionRefused(path)


@unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlinks")
class SymlinkEscapeTest(_InspectionBoundaryCase):
    def test_a_symlink_leaving_the_package_is_refused(self):
        link = self.package / "evidence" / "escape.json"
        link.symlink_to(self.outside)

        # Precondition: the link really does reach the outside file, so this is an
        # escape rather than a broken link.
        self.assertTrue(link.is_file())
        self.assertIn(SENTINEL, link.read_text(encoding="utf-8"))

        self.declare("evidence/escape.json")
        self.assertInspectionRefused("symlink to a file outside the package")

    def test_a_symlink_to_a_directory_outside_the_package_is_refused(self):
        outside_dir = self.root / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "secret.json").write_text(SENTINEL + "\n", encoding="utf-8")

        (self.package / "evidence" / "linked").symlink_to(
            outside_dir, target_is_directory=True
        )
        self.declare("evidence/linked/secret.json",
                     hashlib.sha256((SENTINEL + "\n").encode()).hexdigest())
        self.assertInspectionRefused("symlink to a directory outside the package")

    def test_a_symlink_staying_inside_the_package_is_inspected(self):
        """Containment is the rule, not a blanket ban on symlinks."""
        alias = self.package / "evidence" / "alias.json"
        alias.symlink_to(self.package / "evidence" / "policy.json")

        manifest = json.loads(self.pristine_manifest)
        self.declare("evidence/alias.json", manifest["files"]["evidence/policy.json"])

        completed = run_aura("package", str(self.package), "--json")
        self.assertEqual(EXIT_OK, completed.returncode, completed.stderr)
        entry = next(e for e in json.loads(completed.stdout)["files"]
                     if e["path"] == "evidence/alias.json")
        self.assertTrue(entry["declared"])
        self.assertTrue(entry["present"])


class LegitimateInternalPathTest(_InspectionBoundaryCase):
    """The boundary check must not cost the command its actual job."""

    def test_a_normal_package_is_still_inspected(self):
        completed = run_aura("package", str(self.package))
        self.assertEqual(EXIT_OK, completed.returncode, completed.stderr)
        for path in ("manifest.json", "evidence/audit.jsonl",
                     "evidence/policy.json", "evidence/genesis.json"):
            self.assertIn(path, completed.stdout)
        self.assertIn("THE EVIDENCE", completed.stdout)

    def test_a_declared_file_nested_inside_the_package_is_inspected(self):
        extra = self.package / "evidence" / "nested" / "note.txt"
        extra.parent.mkdir(parents=True)
        extra.write_text("inside the package\n", encoding="utf-8")
        self.declare("evidence/nested/note.txt",
                     hashlib.sha256(extra.read_bytes()).hexdigest())

        described = json.loads(
            run_aura("package", str(self.package), "--json").stdout
        )
        entry = next(e for e in described["files"]
                     if e["path"] == "evidence/nested/note.txt")
        self.assertTrue(entry["declared"])
        self.assertTrue(entry["present"])

        # And absence is still reported, rather than every declared path now
        # reading as present.
        extra.unlink()
        described = json.loads(
            run_aura("package", str(self.package), "--json").stdout
        )
        entry = next(e for e in described["files"]
                     if e["path"] == "evidence/nested/note.txt")
        self.assertFalse(entry["present"])

    def test_the_package_the_product_loop_produces_still_inspects_and_verifies(self):
        self.assertEqual(EXIT_OK, run_aura("package", str(self.package)).returncode)
        self.assertEqual(0, run_aura("verify", str(self.package)).returncode)


class ExternalTargetIsNeverReadTest(_InspectionBoundaryCase):
    """The refusal happens before the outside file is read, not after.

    ``io.open`` is where every read in this command ends up: ``Path.read_text``
    and ``Path.read_bytes`` both go through it. Recording it for the duration of
    one in-process run shows exactly which files the inspection opened.
    """

    def run_recorded(self) -> tuple[int, str, list[str]]:
        opened: list[str] = []
        real_open = io.open

        def recording_open(file, *args, **kwargs):
            try:
                opened.append(os.fspath(file))
            except TypeError:          # an already-open file descriptor
                pass
            return real_open(file, *args, **kwargs)

        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch("io.open", recording_open):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = app.aura.main(["package", str(self.package)])
        return status, stdout.getvalue(), opened

    def assertOutsideNotOpened(self, opened: list[str]):
        outside = self.outside.resolve()
        for name in opened:
            self.assertNotEqual(
                outside, Path(name).resolve(),
                f"the inspection opened the file outside the package: {name}",
            )

    def test_a_traversal_declaration_never_opens_the_outside_file(self):
        self.declare("../outside.json")
        status, stdout, opened = self.run_recorded()
        self.assertEqual(EXIT_REFUSED, status)
        self.assertEqual("", stdout)
        self.assertOutsideNotOpened(opened)

    def test_an_absolute_declaration_never_opens_the_outside_file(self):
        self.declare(str(self.outside))
        status, stdout, opened = self.run_recorded()
        self.assertEqual(EXIT_REFUSED, status)
        self.assertEqual("", stdout)
        self.assertOutsideNotOpened(opened)

    @unittest.skipUnless(hasattr(os, "symlink"), "platform has no symlinks")
    def test_a_symlink_escape_never_opens_the_outside_file(self):
        (self.package / "evidence" / "escape.json").symlink_to(self.outside)
        self.declare("evidence/escape.json")
        status, stdout, opened = self.run_recorded()
        self.assertEqual(EXIT_REFUSED, status)
        self.assertEqual("", stdout)
        self.assertOutsideNotOpened(opened)

    def test_a_contained_package_opens_only_files_inside_it(self):
        """The recorder is worth trusting only if it sees the ordinary reads."""
        status, stdout, opened = self.run_recorded()
        self.assertEqual(EXIT_OK, status)
        self.assertIn("THE EVIDENCE", stdout)
        self.assertIn(
            (self.package / "manifest.json").resolve(),
            {Path(name).resolve() for name in opened},
            "the recorder saw no read of the manifest; it is not observing the run",
        )
        self.assertOutsideNotOpened(opened)


class VerifyIsUnchangedTest(_InspectionBoundaryCase):
    """The verdict command keeps its own answer for the same package."""

    def test_an_escaping_declaration_is_still_INVALID_to_verify(self):
        self.declare("../outside.json")
        completed = run_aura("verify", str(self.package))
        self.assertEqual(3, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("INVALID", completed.stdout)

    def test_the_two_commands_refuse_the_same_package_in_their_own_terms(self):
        self.declare("../outside.json")
        self.assertEqual(3, run_aura("verify", str(self.package)).returncode)
        self.assertEqual(EXIT_REFUSED,
                         run_aura("package", str(self.package)).returncode)


if __name__ == "__main__":
    unittest.main()
