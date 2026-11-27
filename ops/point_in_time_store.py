"""Offline point-in-time evidence cut for Football King research.

This checks *claimed* metadata time ordering; it does not authenticate a source,
prove that an observation existed at the stated time, or store the record in an
externally witnessed append-only archive. The returned digest only detects
changes when compared with a separately pinned trusted digest. Never a bet gate.
"""
import hashlib
import json
import re
from datetime import datetime, timezone

SCHEMA = "football-king-point-in-time-cut-v1"
RECORD_KEYS = frozenset({
    "evidence_id", "fixture_id", "kind", "source", "source_group",
    "source_event_id", "source_updated_utc", "captured_utc", "received_utc",
    "available_utc", "raw_sha256",
})
KINDS = frozenset({"fixture", "lineup", "score", "event", "xg", "quote", "context"})
PHASES = frozenset({"PREMATCH", "INPLAY"})
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MAX_RECORDS = 512


def _clock(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError("NAIVE_TIMESTAMP")
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc


def _text(value):
    return (isinstance(value, str) and 1 <= len(value) <= 128
            and value == value.strip() and value.isprintable())


def _sha(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_cut(records, *, fixture_id, kickoff_utc, decision_utc, phase):
    """Validate one evidence set as of a research decision's claimed UTC clock.

    Raises ValueError on the *entire* set rather than dropping rejected rows.
    No raw data, executable quotes, model probabilities or match results are
    stored, and external source/time authentication is deliberately not claimed.
    """
    if not _text(fixture_id) or phase not in PHASES:
        raise ValueError("INVALID_DECISION_IDENTITY")
    kickoff, decision = _clock(kickoff_utc), _clock(decision_utc)
    if (phase == "PREMATCH" and decision >= kickoff) or (phase == "INPLAY" and decision < kickoff):
        raise ValueError("PHASE_DECISION_TIME_CONFLICT")
    if not isinstance(records, list) or not 1 <= len(records) <= MAX_RECORDS:
        raise ValueError("INVALID_EVIDENCE_COLLECTION")
    seen, accepted = set(), []
    for record in records:
        if not isinstance(record, dict) or set(record) != RECORD_KEYS:
            raise ValueError("INVALID_EVIDENCE_RECORD_SCHEMA")
        if any(not _text(record[key]) for key in (
                "evidence_id", "fixture_id", "source", "source_group", "source_event_id")):
            raise ValueError("INVALID_EVIDENCE_IDENTITY")
        if record["fixture_id"] != fixture_id:
            raise ValueError("FIXTURE_ID_MISMATCH")
        if record["kind"] not in KINDS:
            raise ValueError("INVALID_EVIDENCE_KIND")
        if record["evidence_id"] in seen:
            raise ValueError("DUPLICATE_EVIDENCE_ID")
        seen.add(record["evidence_id"])
        if not isinstance(record["raw_sha256"], str) or not HEX64.fullmatch(record["raw_sha256"]):
            raise ValueError("INVALID_RAW_DIGEST")
        clocks = [_clock(record[key]) for key in (
            "source_updated_utc", "captured_utc", "received_utc", "available_utc")]
        if clocks != sorted(clocks):
            raise ValueError("EVIDENCE_TIME_ORDER_CONFLICT")
        if clocks[-1] > decision:
            raise ValueError("EVIDENCE_NOT_AVAILABLE_AT_DECISION")
        canonical = dict(record)
        for key, clock in zip(("source_updated_utc", "captured_utc", "received_utc", "available_utc"), clocks):
            canonical[key] = clock.isoformat().replace("+00:00", "Z")
        accepted.append(canonical)
    accepted.sort(key=lambda item: item["evidence_id"])
    definition = {
        "schema": SCHEMA,
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "decision_utc": decision.isoformat().replace("+00:00", "Z"),
        "phase": phase,
        "evidence": accepted,
    }
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY",
        "fixture_id": fixture_id,
        "decision_utc": definition["decision_utc"],
        "phase": phase,
        "evidence_count": len(accepted),
        "evidence_ids": [row["evidence_id"] for row in accepted],
        "input_sha256": _sha(definition),
        "source_authenticated": False,
        "external_clock_attested": False,
        "raw_payload_digest_independently_verified": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def audit_cut(records, *, fixture_id, kickoff_utc, decision_utc, phase):
    """Fail closed as HOLD, never silently discard a contaminated record."""
    try:
        return build_cut(records, fixture_id=fixture_id, kickoff_utc=kickoff_utc,
                         decision_utc=decision_utc, phase=phase)
    except (TypeError, ValueError, OverflowError) as exc:
        return {
            "schema": SCHEMA, "status": "HOLD", "reason": str(exc),
            "source_authenticated": False, "external_clock_attested": False,
            "positive_ev_verified": False,
            "production_recommendations": "DISABLED",
        }


def verify_pinned_cut(cut, expected_sha256):
    """Require an externally pinned digest; never trust a self-supplied anchor."""
    return (isinstance(cut, dict) and cut.get("status") == "RESEARCH_ONLY"
            and isinstance(expected_sha256, str) and bool(HEX64.fullmatch(expected_sha256))
            and cut.get("input_sha256") == expected_sha256
            and cut.get("production_recommendations") == "DISABLED")
