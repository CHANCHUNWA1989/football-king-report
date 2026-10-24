"""Per-event capture evidence manifest consistency audit.

Manifest must be supplied independently from the forecast history and pinned
using a separately trusted SHA-256 digest. No signature authority is verified.
"""
import hashlib
import json
import re
from pathlib import Path
from offline_capture_evidence import _utc


def assess_pinned_capture_manifest(rows, *, manifest_path, expected_manifest_sha256,
                                   history_sha256):
    hold = {"status": "HOLD", "reason": "UNVERIFIED_CAPTURE_MANIFEST",
            "production_recommendations": "DISABLED"}
    if (not isinstance(rows, list) or not rows
            or not isinstance(history_sha256, str)
            or re.fullmatch(r"[a-fA-F0-9]{64}", history_sha256) is None
            or not isinstance(expected_manifest_sha256, str)
            or re.fullmatch(r"[a-fA-F0-9]{64}", expected_manifest_sha256) is None
            or not isinstance(manifest_path, (str, Path))):
        return hold
    try:
        source = Path(manifest_path)
        if source.stat().st_size > 20_000_000:
            return hold
        with source.open("rb") as stream:
            raw = stream.read(20_000_001)
        if len(raw) > 20_000_000 or hashlib.sha256(raw).hexdigest() != expected_manifest_sha256.lower():
            return hold
        manifest = json.loads(raw)
    except (OSError, ValueError, TypeError, RecursionError, UnicodeDecodeError):
        return hold
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("history_sha256") != history_sha256.lower()
            or not isinstance(manifest.get("captures"), list)
            or len(manifest["captures"]) != len(rows)):
        return hold
    captures = {}
    for capture in manifest["captures"]:
        if not isinstance(capture, dict):
            return hold
        event = capture.get("event_id")
        canonical_event = event.strip() if isinstance(event, str) else None
        stamp = _utc(capture.get("captured_at_utc"))
        source = capture.get("evidence_source")
        if (not isinstance(event, str) or not event.strip() or canonical_event in captures
                or stamp is None or not isinstance(source, str) or not source.strip()):
            return hold
        captures[canonical_event] = stamp
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return hold
        event = row.get("event_id")
        canonical_event = event.strip() if isinstance(event, str) else None
        if (not canonical_event or canonical_event in seen
                or canonical_event not in captures):
            return hold
        seen.add(canonical_event)
        predicted = _utc(row.get("predicted_at_utc"))
        kickoff = _utc(row.get("kickoff_at_utc"))
        if (predicted is None or kickoff is None
                or not predicted <= captures[canonical_event] < kickoff):
            return hold
    return {"status": "RESEARCH_ONLY", "reason": "PER_EVENT_CAPTURE_CLAIMS_CONSISTENT",
            "event_count": len(rows),
            "manifest_sha256": expected_manifest_sha256.lower(),
            "timestamp_authority_verified": False,
            "source_authenticity_verified": False,
            "production_recommendations": "DISABLED"}
