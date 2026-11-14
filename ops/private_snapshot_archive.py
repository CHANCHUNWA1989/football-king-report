"""Local private snapshot archive with exclusive creation and integrity checks.

The archive is not an independent timestamp authority or immutable external ledger.
Do not publish the directory or commit private forecasts.
"""
import json
import os
from pathlib import Path
from ops.private_forecast_snapshot import seal, verify


def store(directory, forecast):
    snapshot = seal(forecast)
    root = Path(directory)
    if root.is_symlink():
        raise ValueError("SYMLINK_ARCHIVE_REJECTED")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("INVALID_ARCHIVE")
    target = root / (snapshot["sha256"] + ".json")
    data = (json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError("SNAPSHOT_ALREADY_EXISTS") from exc
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "sha256": snapshot["sha256"], "archive_written": True,
            "capture_time_independently_attested": False}


def inspect(directory, digest):
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("INVALID_DIGEST")
    root = Path(directory)
    target = root / (digest + ".json")
    if root.is_symlink() or target.is_symlink() or not target.is_file() or target.stat().st_size > 8192:
        raise ValueError("INVALID_ARCHIVE_ENTRY")
    snapshot = json.loads(target.read_text(encoding="utf-8"))
    verify(snapshot)
    if snapshot["sha256"] != digest:
        raise ValueError("ARCHIVE_DIGEST_MISMATCH")
    return snapshot
