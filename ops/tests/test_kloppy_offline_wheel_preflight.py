"""Synthetic standard-library checks. No downloaded wheel or installation."""
import hashlib
import tempfile
import unittest
import warnings
from pathlib import Path
from zipfile import ZipFile

from ops.kloppy_offline_wheel_preflight import (
    FILENAME, PYPI_SHA256, UnsafeWheel, _inspect,
    verify_official_kloppy_wheel,
)


class OfflineKloppyWheelPreflightTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.file = self.folder / FILENAME

    def create(self, *, name="kloppy", version="3.19.1",
               tag="py3-none-any", omit_metadata=False):
        with ZipFile(self.file, "w") as out:
            if not omit_metadata:
                out.writestr("kloppy-3.19.1.dist-info/METADATA",
                             "Metadata-Version: 2.3\nName: " + name +
                             "\nVersion: " + version + "\n")
            out.writestr("kloppy-3.19.1.dist-info/WHEEL",
                         "Wheel-Version: 1.0\nTag: " + tag + "\n")
        return hashlib.sha256(self.file.read_bytes()).hexdigest()

    def test_synthetic_wheel_validates_structure_but_never_promotes(self):
        expected = self.create()
        result = _inspect(self.file, expected)
        self.assertEqual(result["sha256"], expected)
        self.assertFalse(result["native_smoke_passed"])
        self.assertFalse(result["publisher_attestation_independently_verified"])
        self.assertFalse(result["dependencies_locked_and_audited"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_public_preflight_cannot_override_real_pypi_hash(self):
        synthetic = self.create()
        self.assertNotEqual(synthetic, PYPI_SHA256)
        with self.assertRaisesRegex(UnsafeWheel, "WHEEL_SHA256_DOES_NOT_MATCH_PYPI"):
            verify_official_kloppy_wheel(self.file)

    def test_modified_bytes_rejected_even_with_valid_zip_metadata(self):
        before = self.create()
        with self.file.open("ab") as handle:
            handle.write(b"after-download mutation")
        with self.assertRaisesRegex(UnsafeWheel, "WHEEL_SHA256_DOES_NOT_MATCH_PYPI"):
            _inspect(self.file, before)

    def test_mismatched_package_version_or_tag_fail_closed(self):
        for name, version, tag in (
            ("wrong-identity", "3.19.1", "py3-none-any"),
            ("kloppy", "3.18.0", "py3-none-any"),
            ("kloppy", "3.19.1", "py2-none-any"),
        ):
            with self.subTest(name=name, version=version, tag=tag):
                expected = self.create(name=name, version=version, tag=tag)
                with self.assertRaisesRegex(UnsafeWheel, "UNEXPECTED_WHEEL_IDENTITY"):
                    _inspect(self.file, expected)

    def test_metadata_missing_is_not_wheel(self):
        expected = self.create(omit_metadata=True)
        with self.assertRaisesRegex(UnsafeWheel, "EXPECTED_WHEEL_METADATA_MISSING"):
            _inspect(self.file, expected)

    def test_non_zip_payload_rejected_even_with_matching_test_digest(self):
        self.file.write_bytes(b"not a wheel")
        checksum = hashlib.sha256(self.file.read_bytes()).hexdigest()
        with self.assertRaisesRegex(UnsafeWheel, "INVALID_WHEEL_ZIP"):
            _inspect(self.file, checksum)

    def test_wrong_filename_or_missing_file_rejected(self):
        expected = self.create()
        wrong = self.folder / "unapproved-1.0.whl"
        wrong.write_bytes(self.file.read_bytes())
        with self.assertRaisesRegex(UnsafeWheel, "INVALID_WHEEL_FILE_OR_SIZE"):
            _inspect(wrong, expected)
        with self.assertRaisesRegex(UnsafeWheel, "INVALID_WHEEL_FILE_OR_SIZE"):
            _inspect(self.folder / "missing" / FILENAME, expected)

    def test_symlink_candidate_does_not_count_as_official_artifact(self):
        expected = self.create()
        target = self.folder / "real.zip"
        self.file.rename(target)
        self.file.symlink_to(target)
        with self.assertRaisesRegex(UnsafeWheel, "INVALID_WHEEL_FILE_OR_SIZE"):
            _inspect(self.file, expected)

    def test_duplicate_zip_entries_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(self.file, "w") as out:
                out.writestr("kloppy-3.19.1.dist-info/METADATA",
                             "Name: kloppy\nVersion: 3.19.1\n")
                out.writestr("kloppy-3.19.1.dist-info/WHEEL",
                             "Tag: py3-none-any\n")
                out.writestr("kloppy-3.19.1.dist-info/WHEEL",
                             "Tag: py3-none-any\n")
        expected = hashlib.sha256(self.file.read_bytes()).hexdigest()
        with self.assertRaisesRegex(UnsafeWheel, "DUPLICATE_WHEEL_ENTRY"):
            _inspect(self.file, expected)


if __name__ == "__main__":
    unittest.main()
