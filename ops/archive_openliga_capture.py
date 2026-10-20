"""Archive original OpenLigaDB capture bytes after the workflow's independent audit.

This helper does not authenticate signatures or trust verification flags. It
never extracts a tar, changes captured bytes, or touches forecast archives.
"""
import argparse
import ctypes
import errno
import gzip
import io
import json
import os
import re
import stat
import tempfile
import zlib
from datetime import datetime, timezone
from pathlib import Path


FILE_LIMITS = {"openliga-capture.tar": 4_000_000, "capture.sigstore.json": 2_000_000}


def _safe_path(value):
    path = Path(value)
    if ".." in path.parts:
        raise ValueError("INVALID_CAPTURE_PATH_ALIAS")
    path = path.absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("INVALID_CAPTURE_SYMLINK_ANCESTOR")
    return path


def _read_regular(path, limit):
    from ops.openliga_capture_pack import _read_regular as bounded_read
    return bounded_read(path, limit)


def _check_existing(target, payloads):
    if {p.name for p in target.iterdir()} != {name + ".gz" for name in FILE_LIMITS}:
        raise ValueError("INCOMPLETE_OR_UNEXPECTED_CAPTURE_ARCHIVE")
    for name, raw in payloads.items():
        # Bound compressed input as well as decompressed output, including gzip overhead.
        compressed = _read_regular(target / (name + ".gz"), FILE_LIMITS[name] + 65_536)
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
                existing = stream.read(FILE_LIMITS[name] + 1)
        except (OSError, EOFError, zlib.error) as exc:
            raise ValueError("INVALID_EXISTING_CAPTURE_GZIP") from exc
        if existing != raw:
            raise ValueError("IMMUTABLE_CAPTURE_ARCHIVE_COLLISION")


def _publish(stage, target):
    """Linux atomic no-replace publication; fail closed if unsupported."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise OSError(errno.ENOSYS, "ATOMIC_NOREPLACE_UNAVAILABLE")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
                       ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(stage), -100, os.fsencode(target), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, "ATOMIC_NOREPLACE_PUBLICATION_FAILED")


def prepare(proof: Path, destination: Path, run_id: str, attempt: str, *, day=None):
    """Return created relative paths; identical complete archives are immutable no-ops."""
    if any(not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", value) for value in (run_id, attempt)):
        raise ValueError("INVALID_CAPTURE_RUN_ID")
    if day is None:
        day = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    if not isinstance(day, str) or not re.fullmatch(r"[0-9]{4}/[0-9]{2}/[0-9]{2}", day):
        raise ValueError("INVALID_CAPTURE_DAY")
    datetime.strptime(day, "%Y/%m/%d")
    proof, destination = _safe_path(proof), _safe_path(destination)
    if not proof.is_dir() or not destination.is_dir():
        raise ValueError("INVALID_CAPTURE_DIRECTORY")
    if proof == destination or proof in destination.parents or destination in proof.parents:
        raise ValueError("OVERLAPPING_CAPTURE_PATHS")
    if {p.name for p in proof.iterdir()} != set(FILE_LIMITS):
        raise ValueError("CAPTURE_FILE_ALLOWLIST_MISMATCH")
    payloads = {name: _read_regular(proof / name, limit) for name, limit in FILE_LIMITS.items()}
    relative = Path("openliga_capture_provenance") / day / (str(run_id) + "-" + str(attempt))
    target = _safe_path(destination / relative)
    current = destination
    for part in relative.parts:
        current = current / part
        if current.exists() and not current.is_dir():
            raise ValueError("INVALID_CAPTURE_ARCHIVE_PARENT")
    if target.exists():
        _check_existing(target, payloads)
        return []
    # Both original files and every archive parent are checked before any write.
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".openliga-capture-stage-", dir=target.parent) as stage:
        for name, raw in payloads.items():
            (Path(stage) / (name + ".gz")).write_bytes(gzip.compress(raw, mtime=0))
        _safe_path(target)
        if target.exists():
            raise ValueError("IMMUTABLE_CAPTURE_ARCHIVE_COLLISION")
        _publish(stage, target)
    return [(relative / (name + ".gz")).as_posix() for name in FILE_LIMITS]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--day")
    args = parser.parse_args()
    print(json.dumps({"created": prepare(args.proof, args.destination, args.run_id, args.attempt, day=args.day)}))


if __name__ == "__main__":
    main()
