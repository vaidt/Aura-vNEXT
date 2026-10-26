"""Regression controls for raw transport verification and fatal Git integrity errors."""

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / ".github/scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify = load("verify_governance_acquisition_attestation")
acquire = load("acquire_aura_governance_mirrors")


class AcquisitionTests(unittest.TestCase):
    def archive(self, root, mutate):
        payload = {}
        repos = []
        oid = "a" * 40
        for key, url in verify.EXPECTED_REPOSITORIES.items():
            raw = f"ref: refs/heads/main\tHEAD\n{oid}\tHEAD\n{oid}\trefs/heads/main\n".encode()
            refs = f"refs/heads/main\t{oid}\tcommit\n".encode()
            for name, value in [
                ("ls", raw),
                ("refs", refs),
                ("bundle", b"bundle"),
                ("heads", f"{oid} refs/heads/main\n".encode()),
            ]:
                payload[f"{key}/{name}"] = value
            repos.append(
                dict(
                    key=key,
                    remote_url=url,
                    operations=dict(
                        ls_remote=dict(
                            exit_code=0,
                            stdout_path=f"acquisition-work/{key}/ls",
                            stdout_sha256=verify.sha256_bytes(raw),
                            stdout_size_bytes=len(raw),
                        ),
                        clone_mirror=dict(exit_code=0),
                        bundle_create=dict(exit_code=0),
                        fsck=dict(exit_code=0),
                    ),
                    advertised_refs=acquire.parse_ls_remote(raw),
                    advertised_ref_count=2,
                    fsck_status="PASS",
                    bundle_verify_status="PASS",
                    bundle_path=f"{key}/bundle",
                    bundle_path_sha256=verify.sha256_bytes(b"bundle"),
                    local_refs_path=f"{key}/refs",
                    local_refs_sha256=verify.sha256_bytes(refs),
                    local_ref_count=1,
                    bundle_heads_path=f"{key}/heads",
                )
            )
        manifest = dict(
            schema="aura.governance-raw-mirror-acquisition/0.1.0",
            classification="READ_ONLY / FORENSIC / NON_CONSTITUTIVE",
            acquisition_status="COMPLETE_ADVERTISED_REFS",
            fatal_errors=[],
            repositories=repos,
            workflow_commit_sha="b" * 40,
            workflow_ref="workflow",
            run_id="1",
            run_attempt="1",
        )
        mutate(manifest)
        manifest["files"] = [
            dict(path=k, kind="file", size_bytes=len(v), sha256=verify.sha256_bytes(v))
            for k, v in payload.items()
        ]
        raw = json.dumps(manifest).encode()
        payload["manifest.json"] = raw
        payload["manifest.sha256"] = (
            f"{verify.sha256_bytes(raw)}  manifest.json\n".encode()
        )
        archive = root / "evidence.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            for name, data in payload.items():
                info = tarfile.TarInfo("acquisition/" + name)
                info.size = len(data)
                tf.addfile(info, io.BytesIO(data))
        sidecar = root / "evidence.sha256"
        sidecar.write_text(f"{verify.sha256_file(archive)}  {archive.name}\n")
        return (
            archive,
            sidecar,
            dict(
                workflow_sha="b" * 40,
                workflow_ref="workflow",
                run_id="1",
                run_attempt="1",
            ),
        )

    def test_valid_transport_archive(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(
                verify.verify_archive(*self.archive(Path(td), lambda m: None))[
                    "acquisition_status"
                ],
                "COMPLETE_ADVERTISED_REFS",
            )

    def test_self_consistently_rehashed_ref_omission_rejected(self):
        def omit(m):
            m["repositories"][0]["advertised_refs"].pop()
            m["repositories"][0]["advertised_ref_count"] = 1

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "differ from raw transport"):
                verify.verify_archive(*self.archive(Path(td), omit))

    def test_fsck_failure_rejected_even_with_complete_claim(self):
        def fail(m):
            m["repositories"][0]["operations"]["fsck"]["exit_code"] = 1

        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, "fsck"):
                verify.verify_archive(*self.archive(Path(td), fail))

    def test_transport_rejects_malformed_duplicate_and_empty(self):
        for raw in [
            b"",
            b"garbage\n",
            (("a" * 40 + "\trefs/heads/main\n") * 2).encode(),
        ]:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                verify.parse_advertised_transport(raw)

    def test_acquirer_fsck_failure_blocks_completion(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "acquisition-work"

            def command(args, stem, cwd=None):
                stem.parent.mkdir(parents=True, exist_ok=True)
                out = stem.with_suffix(".stdout.raw")
                out.write_bytes(b"")
                err = stem.with_suffix(".stderr.raw")
                err.write_bytes(b"")
                rc = 0
                if "clone" in args:
                    Path(args[-1]).mkdir(parents=True)
                if "fsck" in args:
                    rc = 1
                if "create" in args:
                    Path(args[-2]).write_bytes(b"bundle")
                return dict(
                    exit_code=rc,
                    stdout_path=str(out),
                    stdout_sha256=hashlib.sha256(b"").hexdigest(),
                    stdout_size_bytes=0,
                    stderr_path=str(err),
                )

            with (
                patch.multiple(
                    acquire,
                    ROOT=root,
                    MIRRORS=root / "mirrors",
                    BUNDLES=root / "bundles",
                    LOGS=root / "logs",
                    INVENTORY=root / "inventory",
                    DIST=Path(td) / "dist",
                ),
                patch.object(acquire, "run_command", side_effect=command),
            ):
                # The receipt uses a relative dist path; keep all output in this temporary directory.
                import os

                previous = Path.cwd()
                try:
                    os.chdir(td)
                    rc = acquire.main()
                    manifest = json.loads((root / "manifest.json").read_text())
                finally:
                    os.chdir(previous)
                self.assertEqual(rc, 20)
                self.assertEqual(manifest["acquisition_status"], "BLOCKED")
                self.assertEqual(len(manifest["fatal_errors"]), 2)
                self.assertTrue(all("fsck" in e for e in manifest["fatal_errors"]))
