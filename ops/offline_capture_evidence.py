"""Verify externally pinned evidence of a historical file's prior existence.

A trusted capture timestamp must be supplied independently of the history file.
This does not cryptographically verify the timestamp authority; a real trusted
timestamp service or signed transparency log is needed for stronger provenance.
"""
import re
from datetime import datetime, timezone


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def assess_external_capture_evidence(rows, *, history_sha256,
                                     evidence_sha256, captured_at_utc,
                                     evidence_source):
    hold = {"status": "HOLD", "reason": "UNVERIFIED_CAPTURE_EVIDENCE",
            "production_recommendations": "DISABLED"}
    if (not isinstance(history_sha256, str)
            or not isinstance(evidence_sha256, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", history_sha256) is None
            or history_sha256.lower() != evidence_sha256.lower()
            or not isinstance(evidence_source, str)
            or not evidence_source.strip()
            or not isinstance(rows, list) or not rows):
        return hold
    captured = _utc(captured_at_utc)
    if captured is None:
        return hold
    for row in rows:
        if not isinstance(row, dict):
            return hold
        kickoff = _utc(row.get("kickoff_at_utc"))
        predicted = _utc(row.get("predicted_at_utc"))
        if (kickoff is None or predicted is None
                or not predicted <= captured < kickoff):
            return hold
    return {"status": "RESEARCH_ONLY", "reason": "EXTERNAL_CAPTURE_CLAIM_CONSISTENT",
            "evidence_source": evidence_source,
            "captured_at_utc": captured_at_utc,
            "timestamp_authority_verified": False,
            "source_authenticity_verified": False,
            "production_recommendations": "DISABLED"}
