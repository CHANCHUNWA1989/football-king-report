"""One-read, bounded, fail-closed validation of a KPL research forecast archive.

Defends against V12's verify-then-reopen race and repeated rescans.
This is only an in-memory consistency check, NOT a signed timestamp, WORM
storage, provider authentication, or a licence/right-to-use determination.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from research.kpl_v11_forecast_archive import (
    MAX_ARCHIVE_BYTES, MAX_ROWS, _digest, _time, validate_forecast)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def read_verified_archive_snapshot(path, *, max_bytes=MAX_ARCHIVE_BYTES):
    """Open once, read at most max_bytes+1, validate the chain on those bytes.

    The snapshot and its SHA256 represent the bytes supplied by the local
    filesystem during this read. Filesystem writes may race or whole files
    may be rewritten. No claim of independently witnessed pre-game existence.
    """
    if type(max_bytes) is not int or max_bytes < 1 or max_bytes > MAX_ARCHIVE_BYTES:
        raise ValueError("invalid snapshot size limit")
    location = Path(path)
    if not location.is_file():
        raise ValueError("missing archive")
    try:
        with location.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
    except OSError as exc:
        raise ValueError("archive read failed") from exc
    if len(raw) > max_bytes:
        raise ValueError("oversized archive")
    if not raw:
        raise ValueError("empty archive")
    if not raw.endswith(b"\n"):
        raise ValueError("truncated archive")
    lines = raw.splitlines(keepends=True)
    if len(lines) > MAX_ROWS:
        raise ValueError("archive row limit exceeded")
    previous = "0" * 64
    entries, records = [], []
    prediction_ids, slots = set(), set()
    last_at = None
    for line in lines:
        if not line.endswith(b"\n") or not line.strip():
            raise ValueError("truncated archive")
        try:
            item = json.loads(line, object_pairs_hook=_reject_duplicate_keys,
                              parse_constant=lambda value: (_ for _ in ()).throw(
                                  ValueError("non-finite JSON value")))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("invalid archive JSON") from exc
        if not isinstance(item, dict) or set(item) != {"forecast", "previous_hash", "entry_hash"}:
            raise ValueError("invalid archive row")
        row = item["forecast"]
        validate_forecast(row)
        expected = _digest(previous, row)
        if item["previous_hash"] != previous or item["entry_hash"] != expected:
            raise ValueError("forecast archive chain mismatch")
        pred_id = row["prediction_id"]
        slot = (row["series_id"], row["game_number"])
        if pred_id in prediction_ids or slot in slots:
            raise ValueError("duplicate archived forecast/game")
        timestamp = _time(row["forecast_at"])
        if last_at is not None and timestamp <= last_at:
            raise ValueError("archive time not strictly increasing")
        prediction_ids.add(pred_id)
        slots.add(slot)
        last_at = timestamp
        previous = expected
        records.append(row)
        entries.append({"forecast": row, "entry_hash": expected})
    return {
        "entries": entries,
        "records": records,
        "head_hash": previous,
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "archive_bytes": len(raw),
        "external_immutable_anchor_verified": False,
        "source_authenticity_verified": False,
        "research_only": True,
        "live_execution_allowed": False}
