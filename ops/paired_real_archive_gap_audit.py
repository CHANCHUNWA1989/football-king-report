"""Audit *actual legacy archive bytes* for A/Penaltyblog pairing readiness.

No network, model fitting, data promotion or implicit conversion of legacy
'AB' or 'C' vectors to Penaltyblog. All historical records are unverified.
A Git blob digest confirms bytes against an independently supplied Git ref,
but does not certify source origin, timestamp or bookmaker execution.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha1
import json
import math
import os
from pathlib import Path
import re
import stat

SCHEMA = "football-king-legacy-penaltyblog-pair-gap-v1"
ARCHIVE_SCHEMA = "football-king-forward-research-1"
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 5000
CORE = {
    "key", "league", "kickoff_utc", "forecast_utc", "market_utc",
    "y", "p", "m", "fixture_result_source_independently_verified",
    "production_recommendations",
}
OPTIONAL = {
    "ab", "ab_model", "c", "c_model", "forecast_event_id",
    "independently_verified", "eligible_for_model_scoring",
    "source_fixture_identity", "source_fixture_identity_status",
}
AB_LABEL = "probability-shrink-to-uniform-fixed-0.15-v1"
C_LABEL = "market-anchored-fixed-25pct-model-75pct-consensus-v1"


def _hold(reason, **extra):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "model_promoted": False,
        "paired_penaltyblog_forecasts_certified": 0,
        "certified_prospective_samples": 0,
        "source_authenticity_verified": False,
        "forecast_external_timestamp_verified": False,
        "result_truth_independently_verified": False,
        "market_quote_executable_verified": False,
        "eligible_for_model_scoring": False,
        **extra,
    }


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _nonfinite(_):
    raise ValueError("NONFINITE_JSON")


def _utc(value):
    if type(value) is not str or not 1 <= len(value) <= 70:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("INVALID_TIMESTAMP")
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("INVALID_TIMESTAMP") from None


def _p3(value):
    return (type(value) is list and len(value) == 3
            and all(type(v) in (int, float) and math.isfinite(v)
                    and 0 <= v <= 1 for v in value)
            and abs(sum(value) - 1) <= 0.002)


def audit_bytes(raw, *, expected_git_blob_sha1):
    """Only inventory the historical schema; no betting/model scoring."""
    if (type(expected_git_blob_sha1) is not str
            or not re.fullmatch(r"[0-9a-f]{40}", expected_git_blob_sha1)):
        return _hold("INVALID_PINNED_GIT_BLOB_SHA")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES:
        return _hold("INVALID_ARCHIVE_BYTE_SIZE")
    actual = sha1(b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw).hexdigest()
    if actual != expected_git_blob_sha1:
        return _hold("ARCHIVE_GIT_BLOB_SHA_MISMATCH")
    try:
        doc = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
        if (type(doc) is not dict or doc.get("schema") != ARCHIVE_SCHEMA
                or doc.get("production_recommendations") != "DISABLED"
                or doc.get("results_independently_verified") is not False
                or doc.get("profitability_verified") is not False
                or type(doc.get("samples")) is not list
                or not 0 < len(doc["samples"]) <= MAX_ROWS
                or type(doc.get("n")) is not int
                or doc["n"] != len(doc["samples"])):
            raise ValueError("UNSAFE_OR_UNEXPECTED_ARCHIVE")
        _utc(doc["checked_utc"])
        counts = {
            "legacy_p_model_vectors": 0,
            "legacy_m_market_probability_vectors": 0,
            "legacy_ab_shrink_vectors_not_penaltyblog": 0,
            "legacy_c_market_anchored_vectors_not_penaltyblog": 0,
            "rows_with_forecast_event_id_unattested": 0,
            "rows_with_native_source_fixture_id_unattested": 0,
            "rows_with_independent_prematch_signer_proof": 0,
            "rows_with_penaltyblog_native_forecast_snapshot": 0,
            "rows_with_authenticated_executable_quote": 0,
            "rows_with_authenticated_result_original": 0,
        }
        seen = set()
        for row in doc["samples"]:
            if (type(row) is not dict or not CORE.issubset(row)
                    or set(row) - CORE - OPTIONAL):
                raise ValueError("UNEXPECTED_LEGACY_ROW_SCHEMA")
            key = row["key"]
            if type(key) is not str or key in seen:
                raise ValueError("DUPLICATE_OR_INVALID_FIXTURE_KEY")
            seen.add(key)
            try:
                parsed = json.loads(key)
            except (ValueError, TypeError) as exc:
                raise ValueError("INVALID_LEGACY_FIXTURE_KEY") from exc
            if (type(parsed) is not list or len(parsed) != 4
                    or any(type(x) is not str or not x for x in parsed)
                    or parsed[0] != row["league"]
                    or parsed[1] == parsed[2]
                    or _utc(parsed[3]) != _utc(row["kickoff_utc"])):
                raise ValueError("INVALID_LEGACY_FIXTURE_KEY")
            if (not _utc(row["market_utc"]) <= _utc(row["forecast_utc"])
                    < _utc(row["kickoff_utc"])):
                raise ValueError("INVALID_LEGACY_CHRONOLOGY")
            if type(row["y"]) is not int or row["y"] not in (0, 1, 2):
                raise ValueError("INVALID_LEGACY_OUTCOME")
            if not _p3(row["p"]) or not _p3(row["m"]):
                raise ValueError("INVALID_LEGACY_PROBABILITIES")
            if (row["production_recommendations"] != "DISABLED"
                    or row["fixture_result_source_independently_verified"] is not False
                    or row.get("independently_verified", False) is not False
                    or row.get("eligible_for_model_scoring", False) is not False):
                raise ValueError("SELF_CERTIFIED_LEGACY_RECORD_REJECTED")
            counts["legacy_p_model_vectors"] += 1
            counts["legacy_m_market_probability_vectors"] += 1
            for prefix, label, counter in (
                ("ab", AB_LABEL, "legacy_ab_shrink_vectors_not_penaltyblog"),
                ("c", C_LABEL, "legacy_c_market_anchored_vectors_not_penaltyblog"),
            ):
                present = prefix in row or (prefix + "_model") in row
                if present:
                    if (row.get(prefix + "_model") != label
                            or not _p3(row.get(prefix))):
                        raise ValueError("UNRECOGNIZED_LEGACY_CHALLENGER")
                    counts[counter] += 1
            if "forecast_event_id" in row:
                if type(row["forecast_event_id"]) is not str or not row["forecast_event_id"]:
                    raise ValueError("INVALID_UNATTESTED_EVENT_ID")
                counts["rows_with_forecast_event_id_unattested"] += 1
            if "source_fixture_identity" in row:
                ident = row["source_fixture_identity"]
                if (type(ident) is not dict or
                        type(ident.get("provider")) is not str or
                        type(ident.get("match_id")) is not str):
                    raise ValueError("INVALID_UNATTESTED_SOURCE_ID")
                counts["rows_with_native_source_fixture_id_unattested"] += 1
        return _hold(
            "LEGACY_A_M_AB_C_NOT_AUTHENTICATED_PENALTYBLOG_PAIRS",
            archive_git_blob_sha1_matched=True,
            archive_bytes_size=len(raw),
            legacy_settled_research_rows=len(doc["samples"]),
            **counts,
            cohort_reinterpretation_blocked=True,
            note=("Historical p/m/ab/c fields are NOT independently witnessed "
                  "original A or Penaltyblog forecasts, nor tradable quotes. "
                  "Missing provenance cannot be backfilled retrospectively."),
        )
    except (ValueError, TypeError, KeyError, OverflowError, UnicodeError) as exc:
        reason = str(exc)
        return _hold(reason if len(reason) < 100 else "INVALID_ARCHIVE")


def _read_bounded(path):
    file = Path(path)
    if any(part.is_symlink() for part in (file, *file.parents)):
        raise ValueError("UNSAFE_ARCHIVE_SYMLINK")
    fd = os.open(file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) |
                 getattr(os, "O_NONBLOCK", 0))
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_BYTES:
            raise ValueError("INVALID_ARCHIVE_FILE_TYPE_OR_SIZE")
        data = bytearray()
        while len(data) <= MAX_BYTES:
            part = os.read(fd, min(65536, MAX_BYTES + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        if len(data) != info.st_size:
            raise ValueError("ARCHIVE_FILE_CHANGED_DURING_READ")
        return bytes(data)
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pinned legacy paired-model gap audit")
    parser.add_argument("--archive", required=True)
    parser.add_argument("--expected-git-blob-sha1", required=True)
    args = parser.parse_args(argv)
    try:
        raw = _read_bounded(args.archive)
        result = audit_bytes(raw, expected_git_blob_sha1=args.expected_git_blob_sha1)
    except (ValueError, OSError) as exc:
        result = _hold(str(exc) if len(str(exc)) < 100 else "ARCHIVE_UNREADABLE")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, allow_nan=False))
    return 0 if result.get("archive_git_blob_sha1_matched") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
