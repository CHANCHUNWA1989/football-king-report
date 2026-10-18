"""Immutable byte-preservation tests; fixture signatures are deliberately fake."""
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from archive_forecast_provenance import prepare


FILES = (
    "shadow.json", "paired.json", "slate.json", "research.sigstore.json",
    "shadow.verification.json", "paired.verification.json", "slate.verification.json",
    "negative_checks.json", "tampered.rejection.log", "wrong-source.rejection.log",
)


class ArchiveForecastProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.proof = self.root / "proof"
        self.proof.mkdir()
        self.destination = self.root / "repo"
        self.destination.mkdir()
        for name in FILES:
            if name.endswith(".log"):
                raw = b"deliberately fake rejection output\n"
            elif name.endswith(".verification.json"):
                raw = b'[{"attestation":{},"verificationResult":{}}]\n'
            elif name == "negative_checks.json":
                raw = b'{"tampered_subject_rejected":true,"wrong_source_digest_rejected":true}\n'
            elif name == "research.sigstore.json":
                raw = b'{"mediaType":"fake","verificationMaterial":{},"dsseEnvelope":{}}\n'
            else:
                raw = ('{ "note": "研究測試", "production_recommendations": "DISABLED" }\n').encode()
            (self.proof / name).write_bytes(raw)
        self.archive = self.destination / "forecast_provenance/2026/10/18/123-1"

    def prepare(self, **options):
        values = {"run_id": "123", "attempt": "1", "day": "2026/10/18"}
        values.update(options)
        return prepare(self.proof, self.destination, **values)

    def assert_no_archive_files(self):
        self.assertEqual(list(self.destination.rglob("*.*")), [])

    def test_all_ten_original_bytes_round_trip_without_authentication_claims(self):
        created = self.prepare()
        self.assertEqual(set(created), {
            "forecast_provenance/2026/10/18/123-1/" + name + ".gz" for name in FILES})
        for name in FILES:
            payload = (self.archive / (name + ".gz")).read_bytes()
            self.assertEqual(payload[4:8], b"\0\0\0\0")
            self.assertEqual(gzip.decompress(payload), (self.proof / name).read_bytes())
        self.assertEqual(set(p.name for p in self.archive.iterdir()), {n + ".gz" for n in FILES})

    def test_identical_rerun_changes_nothing(self):
        self.prepare()
        before = {p: p.read_bytes() for p in self.archive.iterdir()}
        self.assertEqual(self.prepare(), [])
        self.assertEqual(before, {p: p.read_bytes() for p in self.archive.iterdir()})

    def test_different_bytes_never_overwrite_existing_evidence(self):
        self.prepare()
        before = {p: p.read_bytes() for p in self.archive.iterdir()}
        (self.proof / "shadow.json").write_bytes(b'{"changed":true}\n')
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(before, {p: p.read_bytes() for p in self.archive.iterdir()})

    def test_missing_last_file_is_rejected_before_any_archive_write(self):
        (self.proof / FILES[-1]).unlink()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assert_no_archive_files()

    def test_extra_private_or_nested_files_are_not_admitted(self):
        for name in ("private.json", "nested"):
            with self.subTest(name=name):
                extra = self.proof / name
                if name == "nested":
                    extra.mkdir()
                else:
                    extra.write_text("{}")
                with self.assertRaises(ValueError):
                    self.prepare()
                extra.rmdir() if extra.is_dir() else extra.unlink()
                self.assert_no_archive_files()

    def test_invalid_json_shapes_and_nonfinite_values_are_rejected(self):
        examples = (("shadow.json", b"[]"), ("research.sigstore.json", b"[]"),
                    ("paired.verification.json", b"{}"), ("paired.verification.json", b"[]"),
                    ("paired.verification.json", b"[true]"), ("slate.json", b"{broken"),
                    ("slate.json", b'{"not_json":NaN}'),
                    ("negative_checks.json", b'{"tampered_subject_rejected":true}'))
        for name, raw in examples:
            with self.subTest(name=name, raw=raw):
                original = (self.proof / name).read_bytes()
                (self.proof / name).write_bytes(raw)
                with self.assertRaises(ValueError):
                    self.prepare()
                (self.proof / name).write_bytes(original)
                self.assert_no_archive_files()

    def test_invalid_last_log_and_oversize_file_leave_no_partial_archive(self):
        path = self.proof / FILES[-1]
        for raw in (b"", b"\xff", b"x" * 257):
            with self.subTest(raw=raw[:10]):
                path.write_bytes(raw)
                with patch("archive_forecast_provenance.MAX_FILE_BYTES", 256):
                    with self.assertRaises(ValueError):
                        self.prepare()
                self.assert_no_archive_files()

    def test_path_traversal_unicode_digits_and_invalid_calendar_dates_are_rejected(self):
        for options in ({"run_id": "../123"}, {"attempt": "1/2"}, {"run_id": "１２３"},
                        {"attempt": True}, {"day": "2026/../18"}, {"day": "2026/02/30"},
                        {"day": "2026/1/18"}, {"day": "2026/１０/18"}):
            with self.subTest(options=options):
                with self.assertRaises(ValueError):
                    self.prepare(**options)
                self.assert_no_archive_files()

    def test_symlink_input_is_rejected(self):
        original = self.root / "original.json"
        path = self.proof / "shadow.json"
        path.rename(original)
        path.symlink_to(original)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assert_no_archive_files()

    def test_symlink_destination_parent_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.destination / "forecast_provenance").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(list(outside.iterdir()), [])

    def test_late_existing_collision_does_not_create_earlier_files(self):
        self.archive.mkdir(parents=True)
        collision = self.archive / (FILES[-1] + ".gz")
        collision.write_bytes(gzip.compress(b"different bytes", mtime=0))
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(list(self.archive.iterdir()), [collision])
        self.assertEqual(gzip.decompress(collision.read_bytes()), b"different bytes")

    def test_existing_target_symlink_never_changes_its_destination(self):
        self.prepare()
        outside = self.root / "old-evidence.gz"
        outside.write_bytes(b"must stay unchanged")
        target = self.archive / (FILES[-1] + ".gz")
        target.unlink()
        target.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(outside.read_bytes(), b"must stay unchanged")

    def test_staging_failure_cannot_publish_half_a_run(self):
        with patch("archive_forecast_provenance.os.rename", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.prepare()
        self.assertFalse(self.archive.exists())
        self.assert_no_archive_files()


if __name__ == "__main__":
    unittest.main()
