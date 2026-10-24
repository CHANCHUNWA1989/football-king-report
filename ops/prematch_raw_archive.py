"""Tamper-evident local archive for raw odds responses.

The SHA-256 pin protects bytes only; it does not authenticate a provider.
"""
import hashlib
import json
import os
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
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(target, flags, 0o600)
    except FileExistsError:
        if replay_response(target, expected_sha256=digest) != raw:
            raise ValueError("existing archive mismatch")
        return {"path": str(target), "sha256": digest, "byte_count": len(raw)}
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {"path": str(target), "sha256": digest, "byte_count": len(raw)}


def replay_response(path, *, expected_sha256):
    if (not isinstance(expected_sha256, str) or len(expected_sha256) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_sha256)):
        raise ValueError("invalid digest")
    source = Path(path)
    if source.is_symlink() or source.stat().st_size > 1_000_000:
        raise ValueError("invalid archive file")
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("archive digest mismatch")
    return raw
