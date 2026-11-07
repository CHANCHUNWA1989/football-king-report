"""Prepare only an allowed 64-char watchlist digest for GH Actions witness signing.

This is not proof of a real watchlist or externally authenticated kickoff.
No raw bookmaker odds, team details, API keys, or predictions are uploaded.
"""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from ops.research_watchlist_review import _time


def subject(manifest_sha256, earliest_kickoff_utc, *, now=None):
    if not isinstance(manifest_sha256, str) or not re.fullmatch(
            r"[0-9a-f]{64}", manifest_sha256):
        raise ValueError("INVALID_WATCHLIST_MANIFEST_DIGEST")
    kickoff = _time(earliest_kickoff_utc)
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("INVALID_WITNESS_PREPARATION_CLOCK")
    if not now.astimezone(timezone.utc) + timedelta(minutes=10) < kickoff:
        raise ValueError("NOT_EARLY_ENOUGH_FOR_RECORDED_KICKOFF")
    return (manifest_sha256 + "\n").encode("ascii")


def main():
    data = subject(os.environ.get("MANIFEST_SHA256"),
                   os.environ.get("EARLIEST_KICKOFF_UTC"))
    target = Path("watchlist-manifest-sha256.txt")
    # Exclusive, non-overwriting creation of the digest-only artifact.
    with target.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    print("PREMATCH_DIGEST_ONLY_SUBJECT_CREATED: RESEARCH_HOLD")


if __name__ == "__main__":
    main()
