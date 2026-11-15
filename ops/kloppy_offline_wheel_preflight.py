"""Check one local official Kloppy wheel before an isolated native smoke.

No network, installation, match data or provider secrets. A matching file
hash is NOT a signed package attestation, transitive dependency approval,
data-use license, or approval for production predictions.
"""
import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

VERSION = "3.19.1"
FILENAME = "kloppy-3.19.1-py3-none-any.whl"
# PyPI official 2026-10-03 built wheel; documented on pypi.org/project/kloppy/3.19.1/
PYPI_SHA256 = "bdb468cc7b23a6c58276fdd8dbdb9c331e8cf4be8b721fdb97b7ec69d186b5ba"
MAX_SIZE_BYTES = 64 * 1024 * 1024
MAX_ENTRIES = 4096
MAX_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ENTRY_BYTES = 64 * 1024 * 1024
MAX_COMPRESSION_RATIO = 500
MAX_METADATA_BYTES = 512 * 1024
MAX_WHEEL_INFO_BYTES = 64 * 1024


class UnsafeWheel(ValueError):
    """The selected local wheel is not the exact approved PyPI artifact."""



def _preflight_archive_entries(archive):
    """Reject unsafe ZIP member metadata before reading compressed content.

    Paths and entry types are checked even though this preflight never
    extracts a wheel; prevent unsafe archives reaching any future installer.
    Bounded counts/sizes and expansion ratios avoid cheap ZIP bombs during
    the subsequent metadata read and archive.testzip().
    """
    entries = archive.infolist()
    if not entries or len(entries) > MAX_ENTRIES:
        raise UnsafeWheel("UNSAFE_WHEEL_ENTRY")
    seen = set()
    expanded = 0
    for info in entries:
        name = info.filename
        parts = name.rstrip("/").split("/")
        if (not name or len(name) > 512 or name.startswith("/")
                or "\\" in name or ":" in parts[0]
                or any(part in ("", ".", "..") for part in parts)
                or name in seen or info.flag_bits & 1):
            raise UnsafeWheel("UNSAFE_WHEEL_ENTRY")
        seen.add(name)
        mode = stat.S_IFMT(info.external_attr >> 16)
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise UnsafeWheel("UNSAFE_WHEEL_ENTRY")
        expanded += info.file_size
        if (info.file_size > MAX_ENTRY_BYTES
                or expanded > MAX_UNCOMPRESSED_BYTES
                or (info.file_size > 1024 * 1024
                    and info.file_size > MAX_COMPRESSION_RATIO
                    * max(1, info.compress_size))):
            raise UnsafeWheel("UNSAFE_WHEEL_EXPANSION")
        if (name == "kloppy-3.19.1.dist-info/METADATA"
                and info.file_size > MAX_METADATA_BYTES
                or name == "kloppy-3.19.1.dist-info/WHEEL"
                and info.file_size > MAX_WHEEL_INFO_BYTES):
            raise UnsafeWheel("UNSAFE_WHEEL_EXPANSION")


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
            _preflight_archive_entries(archive)
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
