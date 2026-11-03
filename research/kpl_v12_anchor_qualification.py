"""KPL V12 offline anchor receipt and holdout qualification screen.

This is ONLY a local consistency checker. It cannot witness, sign, timestamp,
authenticate or store data externally; it never verifies licensing, outcomes
or provider identity. No network access, betting, real-market code or models.
"""
from __future__ import annotations

import json
from pathlib import Path

from research.kpl_v11_forecast_archive import (
    MAX_ARCHIVE_BYTES, _ident, _time, verify_archive, chronological_holdout)

TARGETS = frozenset({"INDEPENDENT_TIMESTAMP_SERVICE", "EXTERNAL_IMMUTABLE_STORE"})
RECEIPT_KEYS = frozenset({
    "record_index", "head_hash", "prediction_id", "issuer_id",
    "anchor_target", "received_at"})


def _archive_records(path):
    """Verify V11 hash chain *then* read indexed hashes for prefix comparison."""
    location = Path(path)
    if not location.is_file():
        raise ValueError("missing archive")
    verified = verify_archive(location)
    if not verified["records"]:
        raise ValueError("empty archive")
    if location.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("oversized archive")
    entries = []
    with location.open(encoding="utf-8") as file:
        for line in file:
            item = json.loads(line)
            entries.append({"head_hash": item["entry_hash"],
                            "forecast": item["forecast"]})
    if len(entries) != len(verified["records"]):
        raise ValueError("archive changed during inspection")
    return entries


def build_anchor_request(archive_path, record_index, *, requested_at,
                         anchor_target="INDEPENDENT_TIMESTAMP_SERVICE"):
    """Prepare a request for a genuinely independent external witness.

    Returned JSON is *not* sent anywhere and does not prove when an archive
    existed. A future authorized provider can accept this exact request, then
    separately authenticate its receipt with public-key or trusted-service
    evidence. Do not regard request timestamps as trustworthy by themselves.
    """
    rows = _archive_records(archive_path)
    if type(record_index) is not int or not 1 <= record_index <= len(rows):
        raise ValueError("invalid record index")
    if not isinstance(anchor_target, str) or anchor_target not in TARGETS:
        raise ValueError("invalid anchor target")
    row = rows[record_index - 1]["forecast"]
    now = _time(requested_at)
    if now < _time(row["forecast_at"]):
        raise ValueError("anchor requested before forecast")
    if now >= _time(row["game_start_at"]):
        raise ValueError("anchor requested after game start")
    return {"record_index": record_index,
            "head_hash": rows[record_index - 1]["head_hash"],
            "prediction_id": row["prediction_id"],
            "anchor_target": anchor_target, "requested_at": requested_at,
            "status": "PENDING_EXTERNAL_WITNESS",
            "submitted_to_external_provider": False,
            "external_witness_authenticated": False,
            "research_only": True, "live_execution_allowed": False}


def inspect_anchor_receipt(archive_path, receipt):
    """Check an *untrusted* receipt's fields and hash/time correspondence.

    No status can become VERIFIED because a self-provided issuer_id, timestamp,
    HTTPS link or digest is NOT independent witness evidence.
    """
    reasons = []
    try:
        rows = _archive_records(archive_path)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
        return {"status": "HOLD", "structural_consistency_passed": False,
                "reasons": ["INVALID_OR_MISSING_ARCHIVE"],
                "external_witness_authenticated": False,
                "research_only": True, "live_execution_allowed": False}
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_KEYS:
        reasons.append("INVALID_RECEIPT_FIELDS")
        # Exit before indexing missing or malicious values.
        return {"status": "HOLD", "structural_consistency_passed": False,
                "reasons": reasons, "external_witness_authenticated": False,
                "research_only": True, "live_execution_allowed": False}
    index = receipt["record_index"]
    if type(index) is not int or not 1 <= index <= len(rows):
        reasons.append("INVALID_RECEIPT_INDEX")
    if (not _ident(receipt["prediction_id"])
            or not _ident(receipt["issuer_id"])
            or not isinstance(receipt["anchor_target"], str)
            or receipt["anchor_target"] not in TARGETS):
        reasons.append("INVALID_RECEIPT_IDENTITY")
    h = receipt["head_hash"]
    if not isinstance(h, str) or len(h) != 64 or any(c not in "0123456789abcdef" for c in h):
        reasons.append("INVALID_RECEIPT_HASH")
    if "INVALID_RECEIPT_INDEX" not in reasons:
        row = rows[index - 1]
        if row["head_hash"] != h:
            reasons.append("ANCHOR_HEAD_MISMATCH")
        if row["forecast"]["prediction_id"] != receipt["prediction_id"]:
            reasons.append("ANCHOR_PREDICTION_MISMATCH")
        try:
            witnessed = _time(receipt["received_at"])
            if witnessed < _time(row["forecast"]["forecast_at"]):
                reasons.append("ANCHOR_BEFORE_FORECAST")
            if witnessed >= _time(row["forecast"]["game_start_at"]):
                reasons.append("ANCHOR_NOT_PRE_GAME")
        except (ValueError, TypeError):
            reasons.append("INVALID_RECEIPT_CLOCK")
    else:
        try:
            _time(receipt["received_at"])
        except (ValueError, TypeError):
            reasons.append("INVALID_RECEIPT_CLOCK")
    consistent = not reasons
    return {"status": "HOLD", "structural_consistency_passed": consistent,
            "reasons": reasons or ["EXTERNAL_WITNESS_TRUST_UNVERIFIED"],
            "external_witness_authenticated": False,
            "research_only": True, "live_execution_allowed": False}


def screen_holdout_qualification(archive_path, results, receipts, *,
                                 train_fraction=0.7, min_test=30):
    """Fail closed: assess *technical* chronology/receipt coverage only.

    Even a structurally perfect synthetic example is not eligible for
    authenticated KPL performance or real-money recommendations. This function
    has no interface for switching off HOLD.
    """
    issues = []
    try:
        rows = _archive_records(archive_path)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError):
        return {"status": "HOLD", "technical_preflight_passed": False,
                "train_count": None, "test_count": None,
                "reasons": ["INVALID_OR_MISSING_ARCHIVE"],
                "external_witness_authenticated": False,
                "provider_data_rights_verified": False,
                "result_source_authenticated": False,
                "production_recommendations": "DISABLED",
                "research_only": True, "live_execution_allowed": False}
    forecasts = [x["forecast"] for x in rows]
    size = len(rows)
    train_count = test_count = None
    if not isinstance(receipts, list):
        issues.append("INVALID_RECEIPT_COLLECTION")
    else:
        indices = [r.get("record_index") if isinstance(r, dict) else None for r in receipts]
        if any(type(i) is not int for i in indices) or len(set(indices)) != len(indices):
            issues.append("DUPLICATE_OR_INVALID_RECEIPT_INDEX")
        if len(indices) != size or set(indices) != set(range(1, size + 1)):
            issues.append("ANCHOR_RECEIPT_COVERAGE_INCOMPLETE")
        if len(receipts) > size:
            # Avoid excessive processing of attacker-supplied collections.
            issues.append("TOO_MANY_RECEIPTS")
        else:
            for receipt in receipts:
                checked = inspect_anchor_receipt(archive_path, receipt)
                if not checked["structural_consistency_passed"]:
                    issues.append("ANCHOR_RECEIPT_INVALID")
                    break
    try:
        report = chronological_holdout(
            forecasts, results, train_fraction=train_fraction, min_test=min_test)
        train_count = report["train"]["count"]
        test_count = report["holdout"]["count"]
    except (ValueError, TypeError, KeyError, OverflowError):
        issues.append("HOLDOUT_TEMPORAL_OR_RESULT_INVALID")
    technical = not issues
    return {"status": "HOLD", "technical_preflight_passed": technical,
            "train_count": train_count, "test_count": test_count,
            "reasons": list(dict.fromkeys(issues)) + [
                "EXTERNAL_WITNESS_TRUST_UNVERIFIED",
                "RESULT_SOURCE_TRUST_UNVERIFIED",
                "DATA_RIGHTS_UNVERIFIED",
                "MODEL_CALIBRATION_NOT_VERIFIED"],
            "external_witness_authenticated": False,
            "provider_data_rights_verified": False,
            "result_source_authenticated": False,
            "production_recommendations": "DISABLED",
            "research_only": True, "live_execution_allowed": False}
