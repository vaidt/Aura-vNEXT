"""The clean-checkout user test: the documentation is what is under test.

An independent engineer's first contact with this product is `docs/OPERATING-M0.md`.
The claim that matters is that they can operate it from that document alone, from a
clean checkout, with no knowledge of anything inside `core/` or `app/`.

So the walkthrough in that document is not transcribed here -- it is *extracted from
the document and executed*. If someone edits the documented commands into something
that does not run, this suite fails, which is the only way a documentation claim
stays true. A copy of the commands kept here instead would drift silently, and the
operator would be the one to discover it.

The copy the walkthrough runs in holds no `.git`, no build output, and no compiled
caches, and it runs with the environment cleared: no PYTHONPATH, no inherited state.
Anything the operator is told to do must work from the files alone.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _product import REPO_ROOT

import app.aura as aura

GUIDE = REPO_ROOT / "docs/OPERATING-M0.md"
MARKER = "<!-- operator-walkthrough:"

# Anything a clean checkout does not carry, or that would let hidden state leak in.
NOT_IN_A_CHECKOUT = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "build")


def walkthrough_outputs(walkthrough: str) -> set[str]:
    """Return the top-level paths the walkthrough itself creates.

    A checkout is clean by definition, so it cannot already hold the package the
    operator is about to record. Without this the suite passes on a fresh clone and
    fails on a working tree where someone has run the walkthrough by hand -- and
    `aura record` is right to refuse: overwriting a package would discard evidence.
    """
    return {match.split("/")[0]
            for match in re.findall(r"\./([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*)",
                                    walkthrough)}


def clean_checkout(destination: Path, walkthrough: str) -> None:
    """Copy the repository as a clean checkout of it would arrive.

    Tracked files are the definition of a checkout, so `git ls-files` is asked
    first. Where that cannot answer -- no git, or an exported tree with no
    repository -- everything is copied except what a checkout demonstrably does not
    contain: the ignore list above, and the walkthrough's own outputs.
    """
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
    if tracked.returncode == 0 and tracked.stdout:
        destination.mkdir(parents=True)
        for relative in filter(None, tracked.stdout.split("\0")):
            source = REPO_ROOT / relative
            if not source.is_file():        # a deleted-but-tracked path
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return

    created = walkthrough_outputs(walkthrough)
    shutil.copytree(
        REPO_ROOT, destination,
        ignore=lambda directory, names: set(NOT_IN_A_CHECKOUT(directory, names)) | (
            created if Path(directory) == REPO_ROOT else set()),
    )


def extract_walkthrough(text: str) -> str:
    """Return the shell block the guide marks as the operator walkthrough."""
    start = text.index(MARKER)
    block = re.search(r"```sh\n(.*?)```", text[start:], re.S)
    if block is None:
        raise AssertionError(
            f"{GUIDE.name}: the {MARKER!r} marker is not followed by a ```sh block"
        )
    return block.group(1)


class DocumentedWorkflowTest(unittest.TestCase):
    """CLEAN CHECKOUT -> READ DOCUMENTATION -> RUN WORKFLOW -> VERIFY."""

    @classmethod
    def setUpClass(cls):
        cls.guide = GUIDE.read_text(encoding="utf-8")
        cls.walkthrough = extract_walkthrough(cls.guide)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="aura-clean-checkout-")
        self.addCleanup(self._tmp.cleanup)
        self.checkout = Path(self._tmp.name) / "checkout"
        clean_checkout(self.checkout, self.walkthrough)

    def run_in_checkout(self, script: str) -> subprocess.CompletedProcess:
        """Run a shell script in the clean checkout, with nothing inherited."""
        shell = shutil.which("bash") or "/bin/sh"
        return subprocess.run(
            [shell, "-c", script],
            cwd=self.checkout, capture_output=True, text=True, timeout=300,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                 "HOME": str(self.checkout), "LC_ALL": "C.UTF-8"},
        )

    # ---- the walkthrough itself ---------------------------------------------

    def test_the_documented_walkthrough_runs_and_ends_verified(self):
        completed = self.run_in_checkout(
            "set -e\n" + self.walkthrough
        )
        self.assertEqual(
            completed.returncode, 0,
            f"the documented walkthrough failed.\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertIn("Result: VERIFIED", completed.stdout)

    def test_the_walkthrough_covers_the_documented_workflow(self):
        """CREATE -> INSPECT -> COPY -> VERIFY, all four present."""
        for command in ("record", "package", "verify"):
            self.assertIn(f"app.aura {command}", self.walkthrough,
                          f"the walkthrough never runs `aura {command}`")
        self.assertIn("cp -r", self.walkthrough,
                      "the walkthrough never copies the package before verifying it")

    def test_the_walkthrough_verifies_the_copy_not_the_original(self):
        """The COPY step is the point: a package must survive being moved."""
        verify_line = next(line for line in self.walkthrough.splitlines()
                           if "app.aura verify" in line)
        self.assertIn("delivered-package", verify_line)

    def test_no_placeholder_survives_in_the_walkthrough(self):
        """An operator cannot run `--input-hash <sha256>`."""
        for placeholder in ("<sha256>", "<hex64>", "<package>", "TODO", "..."):
            self.assertNotIn(placeholder, self.walkthrough,
                             f"the walkthrough is not runnable as written: "
                             f"it contains the placeholder {placeholder!r}")

    def test_a_clean_checkout_needs_no_configuration(self):
        """No install step, no service, no network: the guide says so, hold it to it."""
        completed = self.run_in_checkout(
            "set -e\n"
            "python3 -m app.aura verify evidence/examples/aura-evidence-loan-001"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    # ---- the guide must keep telling the truth -------------------------------

    def test_the_documented_exit_statuses_are_the_implemented_ones(self):
        documented = dict(re.findall(r"^\| `(\d+)` \| (.+?) \|$", self.guide, re.M))
        implemented = {
            "0": aura.EXIT_OK,
            "2": aura.EXIT_STATUS["TAMPERED"],
            "3": aura.EXIT_STATUS["INVALID"],
            "64": aura.EXIT_USAGE,
            "65": aura.EXIT_REFUSED,
            "141": aura.EXIT_PIPE,
        }
        for status, value in implemented.items():
            self.assertEqual(int(status), value)
            self.assertIn(status, documented,
                          f"exit status {status} is implemented and not documented")
        self.assertEqual(
            set(documented) - set(implemented), set(),
            "the guide documents an exit status the command line never returns",
        )
        self.assertIn("VERIFIED", documented["0"])
        self.assertIn("TAMPERED", documented["2"])
        self.assertIn("INVALID", documented["3"])

    def test_the_guide_states_the_three_results_and_does_not_collapse_them(self):
        for result in ("VERIFIED", "TAMPERED", "INVALID"):
            self.assertIn(f"**{result}**", self.guide)

    def test_the_guide_preserves_every_disclaimed_equivalence(self):
        """P4: the limits of the claim are part of the product, not a footnote."""
        for disclaimed in ("correctness", "fairness", "legality",
                           "authenticity", "authorship"):
            self.assertIn(f"Integrity ≠ {disclaimed}", self.guide,
                          f"the guide no longer states that integrity is not "
                          f"{disclaimed}")

    def test_the_guide_makes_no_regulatory_or_legal_claim(self):
        """Where a claim like this would be tempting, it is refused instead."""
        self.assertIn("makes no regulatory or legal claim", self.guide)

    def test_the_guide_keeps_the_single_platform_claim(self):
        self.assertIn("single-platform", self.guide)
        self.assertIn("No cross-platform", self.guide)

    def test_every_document_the_guide_links_to_exists(self):
        for target in re.findall(r"\]\((?!https?:)([^)#]+)\)", self.guide):
            with self.subTest(link=target):
                self.assertTrue((GUIDE.parent / target).exists(),
                                f"the guide links to {target}, which does not exist")


if __name__ == "__main__":
    unittest.main()
