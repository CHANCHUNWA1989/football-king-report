"""Archive tests use deliberately unauthenticated fixture bytes."""
import gzip
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ops.archive_openliga_capture import prepare


class ArchiveOpenLigaCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proof = self.root / "proof"
        self.proof.mkdir()
        self.destination = self.root / "repo"
        self.destination.mkdir()
        raw = io.BytesIO()
        with tarfile.open(fileobj=raw, mode="w") as stream:
            item = tarfile.TarInfo("fixture.html")
            item.size = 6
            stream.addfile(item, io.BytesIO(b"\x00html\xff"))
        (self.proof / "openliga-capture.tar").write_bytes(raw.getvalue())
        (self.proof / "capture.sigstore.json").write_bytes(
            b'{ "fixture": "fake", "verified": true }\n')
        self.target = self.destination / "openliga_capture_provenance/2026/10/19/123-2"

    def archive(self, **options):
        args = {"run_id": "123", "attempt": "2", "day": "2026/10/19"}
        args.update(options)
        return prepare(self.proof, self.destination, **args)

    def assert_no_writes(self):
        self.assertEqual(list(self.destination.iterdir()), [])

    def test_exact_original_bytes_and_zero_gzip_mtime(self):
        expected = {"openliga_capture_provenance/2026/10/19/123-2/" + name + ".gz"
                    for name in ("openliga-capture.tar", "capture.sigstore.json")}
        self.assertEqual(set(self.archive()), expected)
        self.assertEqual({p.name for p in self.target.iterdir()},
                         {"openliga-capture.tar.gz", "capture.sigstore.json.gz"})
        for name in ("openliga-capture.tar", "capture.sigstore.json"):
            compressed = (self.target / (name + ".gz")).read_bytes()
            self.assertEqual(compressed[4:8], b"\0\0\0\0")
            self.assertEqual(gzip.decompress(compressed), (self.proof / name).read_bytes())

    def test_deterministic_different_archive_and_identical_rerun_noop(self):
        self.archive()
        before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.target.iterdir()}
        self.assertEqual(self.archive(), [])
        self.assertEqual(before, {p.name: (p.read_bytes(), p.stat().st_mtime_ns)
                                  for p in self.target.iterdir()})
        self.archive(run_id="124")
        other = self.target.with_name("124-2")
        self.assertEqual({p.name: p.read_bytes() for p in other.iterdir()},
                         {name: data[0] for name, data in before.items()})

    def test_conflicting_source_does_not_overwrite_any_existing_archive(self):
        self.archive()
        before = {p.name: p.read_bytes() for p in self.target.iterdir()}
        (self.proof / "capture.sigstore.json").write_bytes(b'{"different":true}')
        with self.assertRaises(ValueError):
            self.archive()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.target.iterdir()})

    def test_missing_extra_directory_and_empty_source_preflight_before_writes(self):
        path = self.proof / "capture.sigstore.json"
        original = path.read_bytes()
        for mutation in ("missing", "directory", "empty", "extra"):
            with self.subTest(mutation=mutation):
                if mutation == "extra":
                    (self.proof / "verification.json").write_text("{}")
                else:
                    path.unlink()
                    if mutation == "directory":
                        path.mkdir()
                    elif mutation == "empty":
                        path.write_bytes(b"")
                with self.assertRaises(ValueError):
                    self.archive()
                self.assert_no_writes()
                if mutation == "extra":
                    (self.proof / "verification.json").unlink()
                elif path.is_dir():
                    path.rmdir()
                elif path.exists():
                    path.unlink()
                path.write_bytes(original)

    def test_both_size_limits_checked_before_writes(self):
        for name in ("openliga-capture.tar", "capture.sigstore.json"):
            with self.subTest(name=name):
                with patch.dict("ops.archive_openliga_capture.FILE_LIMITS", {name: 4}):
                    with self.assertRaises(ValueError):
                        self.archive()
                self.assert_no_writes()

    def test_invalid_run_ids_attempts_and_calendar_dates(self):
        for options in ({"run_id": "0"}, {"attempt": "01"}, {"run_id": 123}, {"run_id": "../123"}, {"run_id": "１２３"},
                        {"run_id": "1" * 21}, {"attempt": "1/2"}, {"attempt": True},
                        {"day": "2026/2/19"}, {"day": "2026/02/30"},
                        {"day": "2026/１０/19"}, {"day": "2026/../19"}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    self.archive(**options)
                self.assert_no_writes()

    def test_default_archive_day_uses_utc(self):
        with patch("ops.archive_openliga_capture.datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 10, 19, 0, 1, tzinfo=timezone.utc)
            self.archive(day=None)
            clock.now.assert_called_once_with(timezone.utc)
        self.assertTrue(self.target.is_dir())

    def test_new_capture_leaves_old_capture_and_forecast_evidence_unchanged(self):
        self.archive()
        frozen = self.destination / "forecast_provenance/old/frozen.json.gz"
        frozen.parent.mkdir(parents=True)
        frozen.write_bytes(b"frozen forecast bytes")
        before = {p: p.read_bytes() for p in self.destination.rglob("*") if p.is_file()}
        self.archive(run_id="124")
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_symlink_or_hardlinked_source_rejected(self):
        path = self.proof / "capture.sigstore.json"
        original = self.root / "original.json"
        path.rename(original)
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                path.symlink_to(original) if kind == "symlink" else os.link(original, path)
                with self.assertRaises(ValueError):
                    self.archive()
                self.assert_no_writes()
                path.unlink()

    def test_symlink_ancestors_and_parent_traversal_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        examples = ((alias / "proof", self.destination),
                    (self.proof, alias / "repo"),
                    (self.root / "proof/../proof", self.destination),
                    (self.proof, self.root / "repo/../repo"))
        for proof, destination in examples:
            with self.subTest(proof=proof, destination=destination):
                with self.assertRaises(ValueError):
                    prepare(proof, destination, "123", "2", day="2026/10/19")
                self.assert_no_writes()

    def test_wrong_destination_or_overlapping_paths_rejected(self):
        missing = self.root / "missing"
        ordinary_file = self.root / "file"
        ordinary_file.write_text("unchanged")
        for destination in (missing, ordinary_file, self.proof, self.root):
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    prepare(self.proof, destination, "123", "2", day="2026/10/19")
                self.assert_no_writes()
        self.assertFalse(missing.exists())
        self.assertEqual(ordinary_file.read_text(), "unchanged")

    def test_archive_parent_symlink_or_file_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        parent = self.destination / "openliga_capture_provenance"
        for kind in ("symlink", "file"):
            with self.subTest(kind=kind):
                parent.symlink_to(outside, target_is_directory=True) if kind == "symlink" else parent.write_text("old")
                with self.assertRaises(ValueError):
                    self.archive()
                self.assertEqual(list(outside.iterdir()), [])
                parent.unlink()
        self.assert_no_writes()

    def test_existing_incomplete_extra_symlink_and_hardlink_files_rejected(self):
        self.archive()
        file = self.target / "capture.sigstore.json.gz"
        raw = file.read_bytes()
        for mutation in ("incomplete", "extra", "symlink", "hardlink", "corrupt", "deflate"):
            with self.subTest(mutation=mutation):
                outside = self.root / "outside.gz"
                outside.write_bytes(raw)
                if mutation == "extra":
                    (self.target / "extra").write_bytes(b"old")
                else:
                    file.unlink()
                    if mutation == "symlink":
                        file.symlink_to(outside)
                    elif mutation == "hardlink":
                        os.link(outside, file)
                    elif mutation == "corrupt":
                        file.write_bytes(b"not gzip")
                    elif mutation == "deflate":
                        file.write_bytes(bytes.fromhex("1f8b08000000000000ff") + b"not deflate data")
                before = {p.name: p.lstat() for p in self.target.iterdir()}
                with self.assertRaises(ValueError):
                    self.archive()
                self.assertEqual(before, {p.name: p.lstat() for p in self.target.iterdir()})
                if mutation == "extra":
                    (self.target / "extra").unlink()
                elif file.exists():
                    file.unlink()
                if mutation != "extra":
                    file.write_bytes(raw)
                outside.unlink()

    def test_staging_write_or_publish_failure_leaves_no_partial_archive(self):
        for target in ("gzip.compress", "_publish"):
            with self.subTest(target=target):
                with patch("ops.archive_openliga_capture." + target, side_effect=OSError("disk failure")):
                    with self.assertRaises(OSError):
                        self.archive()
                self.assertFalse(self.target.exists())
                self.assertEqual(list(self.destination.rglob("*.gz")), [])
                self.assertEqual(list(self.destination.rglob(".openliga-capture-stage-*")), [])

    def test_target_created_during_staging_is_not_overwritten(self):
        compress = gzip.compress

        def collide(raw, *, mtime):
            self.target.mkdir(exist_ok=True)
            return compress(raw, mtime=mtime)

        with patch("ops.archive_openliga_capture.gzip.compress", side_effect=collide):
            with self.assertRaises(ValueError):
                self.archive()
        self.assertEqual(list(self.target.iterdir()), [])
        self.assertEqual(list(self.destination.rglob(".openliga-capture-stage-*")), [])

    def test_atomic_publish_never_replaces_directory_created_after_preflight(self):
        from ops.archive_openliga_capture import _publish
        def raced(stage, target):
            target.mkdir()
            (target / "sentinel").write_bytes(b"immutable winner")
            return _publish(stage, target)
        with patch("ops.archive_openliga_capture._publish", side_effect=raced):
            with self.assertRaises(FileExistsError):
                self.archive()
        self.assertEqual((self.target / "sentinel").read_bytes(), b"immutable winner")
        self.assertEqual({p.name for p in self.target.iterdir()}, {"sentinel"})
        self.assertEqual(list(self.destination.rglob(".openliga-capture-stage-*")), [])

    def test_cli_returns_same_contract(self):
        result = subprocess.run([sys.executable, "-m", "ops.archive_openliga_capture", "--proof", str(self.proof),
                                 "--destination", str(self.destination), "--run-id", "123",
                                 "--attempt", "2", "--day", "2026/10/19"],
                                check=True, capture_output=True, text=True)
        self.assertEqual(len(json.loads(result.stdout)["created"]), 2)


if __name__ == "__main__":
    unittest.main()
