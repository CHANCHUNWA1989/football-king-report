"""Verify externally pinned historical forecast JSON bytes before offline replay.

Digest pin must come from an independent trusted channel. A matching digest
alone does not prove pre-match capture or third-party authenticity.
"""
import hashlib
import json
import re
from pathlib import Path


def load_pinned_history(path, *, expected_sha256, expected_model_version):
    hold = {"status": "HOLD", "reason": "UNVERIFIED_HISTORICAL_SOURCE",
            "production_recommendations": "DISABLED"}
    if (not isinstance(path, (str, Path))
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) is None
            or not isinstance(expected_model_version, str)
            or not expected_model_version.strip()):
        return hold
    try:
        source = Path(path)
        if source.stat().st_size > 20_000_000:
            return hold
        with source.open("rb") as stream:
            raw = stream.read(20_000_001)
        if len(raw) > 20_000_000:
            return hold
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha256.lower():
            return hold
        document = json.loads(raw)
    except (OSError, ValueError, TypeError, RecursionError, UnicodeDecodeError):
        return hold
    if (not isinstance(document, dict)
            or document.get("schema_version") != 1
            or document.get("model_version") != expected_model_version
            or not isinstance(document.get("rows"), list)
            or not 90 <= len(document["rows"]) <= 100000):
        return hold
    rows = document["rows"]
    for row in rows:
        if (not isinstance(row, dict)
                or row.get("model_version") != expected_model_version
                or not isinstance(row.get("event_id"), str)
                or not row["event_id"].strip()):
            return hold
    return {"status": "RESEARCH_ONLY", "reason": "PINNED_HISTORY_BYTES_MATCH",
            "rows": rows, "row_count": len(rows),
            "sha256": digest, "model_version": expected_model_version,
            "external_timestamp_verified": False,
            "source_authenticity_verified": False,
            "production_recommendations": "DISABLED"}
