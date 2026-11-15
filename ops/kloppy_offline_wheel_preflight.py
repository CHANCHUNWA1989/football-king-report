"""Check one local official Kloppy wheel before an isolated native smoke.

No network, installation, match data or provider secrets. A matching file
hash is NOT a signed package attestation, transitive dependency approval,
data-use license, or approval for production predictions.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

VERSION = "3.19.1"
FILENAME = "kloppy-3.19.1-py3-none-any.whl"
# PyPI official 2026-10-03 built wheel; documented on pypi.org/project/kloppy/3.19.1/
PYPI_SHA256 = "bdb468cc7b23a6c58276fdd8dbdb9c331e8cf4be8b721fdb97b7ec69d186b5ba"
MAX_SIZE_BYTES = 64 * 1024 * 1024


class UnsafeWheel(ValueError):
    """The selected local wheel is not the exact approved PyPI artifact."""


def _inspect(path, expected_sha256):
    """Internal testable inspection. Public API never accepts a hash override."""
    file = Path(path)
    if (file.name != FILENAME or file.is_symlink() or not file.is_file()
            or file.stat().st_size <= 0
            or file.stat().st_size > MAX_SIZE_BYTES):
        raise UnsafeWheel("INVALID_WHEEL_FILE_OR_SIZE")
    digest = hashlib.sha256()
    with file.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected_sha256:
        raise UnsafeWheel("WHEEL_SHA256_DOES_NOT_MATCH_PYPI")
    try:
        with ZipFile(file) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise UnsafeWheel("DUPLICATE_WHEEL_ENTRY")
            meta_path = "kloppy-3.19.1.dist-info/METADATA"
            wheel_path = "kloppy-3.19.1.dist-info/WHEEL"
            if meta_path not in names or wheel_path not in names:
                raise UnsafeWheel("EXPECTED_WHEEL_METADATA_MISSING")
            metadata = archive.read(meta_path).decode("utf-8")
            wheel = archive.read(wheel_path).decode("utf-8")
            if (not any(line.lower() == "name: kloppy" for line in metadata.splitlines())
                    or "Version: " + VERSION not in metadata.splitlines()
                    or "Tag: py3-none-any" not in wheel.splitlines()):
                raise UnsafeWheel("UNEXPECTED_WHEEL_IDENTITY")
            if archive.testzip() is not None:
                raise UnsafeWheel("CORRUPT_WHEEL_FILE")
    except (BadZipFile, UnicodeDecodeError, OSError, ValueError) as exc:
        if isinstance(exc, UnsafeWheel):
            raise
        raise UnsafeWheel("INVALID_WHEEL_ZIP") from exc
    return {
        "status": "LOCAL_WHEEL_HASH_MATCHES_PYPI",
        "wheel": FILENAME,
        "sha256": actual,
        "kloppy_version": VERSION,
        "publisher_attestation_independently_verified": False,
        "dependencies_locked_and_audited": False,
        "provider_data_rights_verified": False,
        "native_smoke_passed": False,
        "production_recommendations": "DISABLED",
    }


def verify_official_kloppy_wheel(path):
    """Exact 3.19.1 artifact only; never trust caller-supplied digest."""
    return _inspect(path, PYPI_SHA256)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline PyPI Kloppy wheel hash preflight")
    parser.add_argument("--wheel", required=True, help="Existing local verified-download candidate")
    args = parser.parse_args(argv)
    try:
        result = verify_official_kloppy_wheel(args.wheel)
    except UnsafeWheel as exc:
        print("HOLD: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
