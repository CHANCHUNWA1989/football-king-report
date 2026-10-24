"""Tamper-evident local archive for raw odds responses.

The SHA-256 pin protects bytes only; it does not authenticate a provider.
"""
import hashlib
import json
import os
import tempfile
import stat
from pathlib import Path


def archive_response(raw, *, directory):
    if not isinstance(raw, bytes) or not raw or len(raw) > 1_000_000:
        raise ValueError("invalid raw response")
    root = Path(directory)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("archive directory must exist and not be a symlink")
    digest = hashlib.sha256(raw).hexdigest()
    name = digest + ".json"
    target = root / name
    # Publish only fully written and synced files; concurrent writers cannot
    # observe or overwrite an incomplete digest-named archive.
    fd, temporary = tempfile.mkstemp(prefix=".odds-", dir=root)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except FileExistsError:
            if replay_response(target, expected_sha256=digest) != raw:
                raise ValueError("existing archive mismatch")
        return {"path": str(target), "sha256": digest, "byte_count": len(raw)}
    finally:
        Path(temporary).unlink(missing_ok=True)


def replay_response(path, *, expected_sha256):
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
        raise ValueError("invalid digest")
    source = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(source, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 1_000_000:
            raise ValueError("invalid archive file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(1_000_001)
    finally:
        os.close(fd)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("archive digest mismatch")
    return raw
