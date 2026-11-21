"""Read-only audit of the REAL first 19 separately sealed Bundesliga forecasts.

Original provider source was observed by a GitHub runner but isn't independently
notarized. The audit checks exact file bytes against a pinned original index,
then checks every per-fixture pre-match provenance and risk flag. Results are
NOT fetched; NO apparent real-world match result can be admitted or scored.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

try:
    from . import identity_ab_forward_seal as seal
    from .team_identity import team_id
except ImportError:
    import identity_ab_forward_seal as seal
    from team_identity import team_id

RUN_DIRECTORY = "42444100017-1"
PINNED_INDEX_GIT_BLOB_SHA1 = "279a9f28ac86e5458de164ec8aad0a8a4f3283c3"
EXPECTED_SOURCE_COMMIT = "5b8653c238f4ff49cac1c78712cc61f3a0065496"
EXPECTED_RAW_SHA256 = "7dc7c02b67ce74be2aaf899d4ea265ee66b5f7f652d8f0ace018ee2314a92de1"
EXPECTED_INPUT_SHA256 = "9c9f0ff9a9e4df6d7a58f9e8209dd4a8a7956cfa1c8c9e6a5efe409739b9e510"
EXPECTED_LEGACY_BLOB_SHA1 = "5216a97e5fac69bd0d0594f28e3b35778f36c62c"
EXPECTED_RECEIVED_UTC = "2026-11-08T03:46:45.944094+00:00"
EXPECTED_RECORD_COUNT = 19
MAX_INDEX_BYTES = 16_384
MAX_RECORD_BYTES = 8_192
INDEX_KEYS = frozenset((
    "schema", "status", "source_response_received_utc", "source_response_sha256",
    "source_commit", "github_run_id", "github_run_attempt", "record_count",
    "record_sha256", "all_forecasts_are_pre_match_and_unsettled",
    "original_source_authenticity_verified", "independently_verified_result_count",
    "production_recommendations",
))
RECORD_KEYS = frozenset((
    "schema", "status", "provider", "provider_native_event_id", "event_id",
    "league", "home", "away", "scheduled_kickoff_utc",
    "source_response_received_utc", "forecast_created_before_scheduled_kickoff",
    "forecast_horizon_at_capture_minutes", "research_coverage",
    "legacy_1x2", "candidate_1x2", "source_response_sha256",
    "normalized_model_input_sha256", "frozen_legacy_source_blob_sha1",
    "candidate_source_commit", "github_run_id", "github_run_attempt",
    "source_independently_authenticated",
    "github_run_timestamp_is_not_cryptographic_notarization",
    "regulation_time_result_verified", "actual_kickoff_authenticated",
    "market_odds_verified", "forecast_calibrated",
    "model_accuracy_improved_proven", "positive_ev_verified",
    "certified_case_count", "production_recommendations",
))


class ForwardArchiveAuditError(ValueError):
    """Constant safe error; never print raw JSON or untrusted strings."""


def _require(condition, code):
    if not condition:
        raise ForwardArchiveAuditError(code)


def _unique_pairs(pairs):
    output = {}
    for key, val in pairs:
        _require(key not in output, "DUPLICATE_ARCHIVED_JSON_KEY")
        output[key] = val
    return output


def _bad_constant(_value):
    raise ForwardArchiveAuditError("NONFINITE_ARCHIVED_JSON")


def _parse(raw, *, expected):
    try:
        result = json.loads(raw.decode("utf-8", "strict"),
                            object_pairs_hook=_unique_pairs,
                            parse_constant=_bad_constant)
    except ForwardArchiveAuditError:
        raise
    except (TypeError, UnicodeError, ValueError, RecursionError):
        raise ForwardArchiveAuditError("INVALID_ARCHIVED_JSON") from None
    _require(type(result) is dict and set(result) == expected,
             "INVALID_ARCHIVED_SCHEMA")
    return result


def _read(root, name, maximum):
    path = root / name
    try:
        before = path.lstat()
        _require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and 0 < before.st_size <= maximum, "UNSAFE_ARCHIVED_FILE")
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK
                     | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            _require((opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                     == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns),
                     "ARCHIVED_FILE_CHANGED")
            raw = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        linked = path.lstat()
        _require((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                 == (linked.st_dev, linked.st_ino, linked.st_size, linked.st_mtime_ns)
                 == (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                 and len(raw) == before.st_size,
                 "ARCHIVED_FILE_CHANGED")
        return raw
    except ForwardArchiveAuditError:
        raise
    except (OSError, TypeError):
        raise ForwardArchiveAuditError("MISSING_OR_UNSAFE_ARCHIVED_FILE") from None


def _git_blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode("ascii")
                        + bytes([0]) + raw).hexdigest()


def _utc(value):
    try:
        return seal._date(value)
    except (seal.SealError, ValueError, TypeError, OverflowError):
        raise ForwardArchiveAuditError("INVALID_ARCHIVED_TIME") from None


def _forecast_vector(vector):
    _require(type(vector) is list and len(vector) == 3
             and all(type(p) in (float, int) and math.isfinite(p)
                     and 0 <= p <= 1 for p in vector)
             and abs(sum(vector)-1) <= 3e-6,
             "INVALID_ARCHIVED_PROBABILITY")
    return vector


def audit(directory, *, as_of_utc=None):
    """Reject any mismatched actual archive; never score pending results."""
    root = Path(directory)
    _require(root.name == RUN_DIRECTORY and root.is_dir() and not root.is_symlink()
             and not any(p.is_symlink() for p in root.parents),
             "UNSAFE_ARCHIVE_DIRECTORY")
    now = _utc(as_of_utc) if as_of_utc is not None else datetime.now(timezone.utc)
    index_raw = _read(root, "index.json", MAX_INDEX_BYTES)
    _require(_git_blob(index_raw) == PINNED_INDEX_GIT_BLOB_SHA1,
             "PINNED_ARCHIVE_INDEX_CHANGED")
    index = _parse(index_raw, expected=INDEX_KEYS)
    _require(index["schema"] == seal.INDEX_SCHEMA
             and index["status"] == "SHADOW_ONLY_UNVERIFIED"
             and index["source_response_received_utc"] == EXPECTED_RECEIVED_UTC
             and index["source_response_sha256"] == EXPECTED_RAW_SHA256
             and index["source_commit"] == EXPECTED_SOURCE_COMMIT
             and index["github_run_id"] == RUN_DIRECTORY.split("-")[0]
             and index["github_run_attempt"] == RUN_DIRECTORY.split("-")[1]
             and type(index["record_count"]) is int
             and index["record_count"] == EXPECTED_RECORD_COUNT
             and index["all_forecasts_are_pre_match_and_unsettled"] is True
             and index["original_source_authenticity_verified"] is False
             and type(index["independently_verified_result_count"]) is int
             and index["independently_verified_result_count"] == 0
             and index["production_recommendations"] == "DISABLED"
             and type(index["record_sha256"]) is dict
             and len(index["record_sha256"]) == EXPECTED_RECORD_COUNT,
             "UNTRUSTED_ARCHIVE_INDEX")
    files = index["record_sha256"]
    _require(all(type(k) is str and re.fullmatch(r"[1-9][0-9]{0,10}\.json", k)
                 and type(v) is str and seal.DIGEST_RE.fullmatch(v)
                 for k,v in files.items()),
             "INVALID_ARCHIVE_FILE_SET")
    try:
        observed_names = {p.name for p in root.iterdir()}
    except OSError:
        raise ForwardArchiveAuditError("UNSAFE_ARCHIVE_DIRECTORY") from None
    _require(observed_names == set(files) | {"index.json"},
             "ARCHIVE_EXTRA_OR_MISSING_FILE")
    capture = _utc(EXPECTED_RECEIVED_UTC)
    counts = {"records": 0, "paired": 0, "legacy_only": 0, "candidate_only": 0,
              "legacy_home_top": 0, "candidate_home_top": 0,
              "prediction_vectors_equal": 0,
              "pending_before_scheduled_kickoff": 0,
              "scheduled_kickoff_elapsed_no_independent_result": 0}
    cases = []
    for name in sorted(files):
        raw = _read(root, name, MAX_RECORD_BYTES)
        _require(hashlib.sha256(raw).hexdigest() == files[name],
                 "ARCHIVED_FORECAST_BYTES_CHANGED")
        row = _parse(raw, expected=RECORD_KEYS)
        native = name[:-5]
        eid = "openligadb:" + native
        _require(row["schema"] == seal.SCHEMA
                 and row["status"] == "SHADOW_ONLY_UNVERIFIED"
                 and row["provider"] == "OpenLigaDB"
                 and row["provider_native_event_id"] == native
                 and row["event_id"] == eid
                 and row["league"] == "bundesliga"
                 and row["source_response_received_utc"] == EXPECTED_RECEIVED_UTC
                 and row["source_response_sha256"] == EXPECTED_RAW_SHA256
                 and row["normalized_model_input_sha256"] == EXPECTED_INPUT_SHA256
                 and row["frozen_legacy_source_blob_sha1"] == EXPECTED_LEGACY_BLOB_SHA1
                 and row["candidate_source_commit"] == EXPECTED_SOURCE_COMMIT
                 and row["github_run_id"] == index["github_run_id"]
                 and row["github_run_attempt"] == index["github_run_attempt"]
                 and row["forecast_created_before_scheduled_kickoff"] is True
                 and row["github_run_timestamp_is_not_cryptographic_notarization"] is True
                 and row["source_independently_authenticated"] is False
                 and row["regulation_time_result_verified"] is False
                 and row["actual_kickoff_authenticated"] is False
                 and row["market_odds_verified"] is False
                 and row["forecast_calibrated"] is False
                 and row["model_accuracy_improved_proven"] is False
                 and row["positive_ev_verified"] is False
                 and type(row["certified_case_count"]) is int
                 and row["certified_case_count"] == 0
                 and row["production_recommendations"] == "DISABLED",
                 "ARCHIVED_UNTRUSTED_AUTHORITY")
        kickoff = _utc(row["scheduled_kickoff_utc"])
        horizon = int((kickoff-capture).total_seconds() // 60)
        _require(kickoff > capture and horizon >= 60
                 and type(row["forecast_horizon_at_capture_minutes"]) is int
                 and row["forecast_horizon_at_capture_minutes"] == horizon,
                 "ARCHIVED_KICKOFF_OR_HORIZON_CHANGED")
        scope = row["research_coverage"]
        _require(scope in ("PAIRED","LEGACY_ONLY","CANDIDATE_ONLY"),
                 "INVALID_ARCHIVED_COVERAGE")
        if scope == "PAIRED":
            _require(type(row["home"]) is str and type(row["away"]) is str
                     and 0 < len(row["home"]) < 110
                     and 0 < len(row["away"]) < 110
                     and team_id("bundesliga", row["home"])
                     != team_id("bundesliga", row["away"]),
                     "INVALID_ARCHIVED_FIXTURE_IDENTITY")
            old = _forecast_vector(row["legacy_1x2"])
            new = _forecast_vector(row["candidate_1x2"])
            counts["legacy_home_top"] += int(old[0] == max(old))
            counts["candidate_home_top"] += int(new[0] == max(new))
            counts["prediction_vectors_equal"] += int(old == new)
        else:
            _require(row["home"] is None and row["away"] is None
                     and row["legacy_1x2"] is None
                     and row["candidate_1x2"] is None,
                     "UNPAIRED_FORECAST_CANNOT_INVENT_PROBABILITIES")
        counts[scope.lower()] += 1
        if now < kickoff:
            state = "PENDING_SCHEDULED_KICKOFF"
            counts["pending_before_scheduled_kickoff"] += 1
        else:
            state = "AWAITING_INDEPENDENT_REGULATION_FT"
            counts["scheduled_kickoff_elapsed_no_independent_result"] += 1
        cases.append({"provider_native_event_id":native,
                      "scheduled_kickoff_utc":kickoff.isoformat(),
                      "forecast_sha256":files[name],
                      "research_coverage":scope,
                      "status":state, "independently_verified":False,
                      "eligible_for_scoring":False})
        counts["records"] += 1
    _require(counts["records"] == EXPECTED_RECORD_COUNT,
             "INCOMPLETE_ARCHIVE")
    return {"schema":"football-king-forward-19-archive-readonly-audit-v1",
            "status":"HOLD",
            "source":"PINNED_GITHUB_RESEARCH_ARCHIVE",
            "github_run_id":index["github_run_id"],
            "as_of_utc":now.isoformat(),
            "forecast_file_count":counts["records"],
            "all_forecast_byte_pins_valid":True,
            "index_pinned_git_blob_sha1":PINNED_INDEX_GIT_BLOB_SHA1,
            "source_response_sha256":EXPECTED_RAW_SHA256,
            "forecast_cohort":counts,
            "cases":cases,
            "original_source_authenticity_independently_proven":False,
            "actual_kickoff_authenticated":False,
            "independent_regulation_ft_result_count":0,
            "scored_result_count":0,
            "model_uplift_proven":False,
            "positive_ev_verified":False,
            "production_recommendations":"DISABLED"}


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True)
    parser.add_argument("--as-of-utc",default=None)
    args=parser.parse_args(argv)
    try:
        output=audit(args.directory,as_of_utc=args.as_of_utc)
        print(json.dumps(output,sort_keys=True))
        return 0
    except (ForwardArchiveAuditError, OSError, ValueError, TypeError):
        print(json.dumps({
            "status":"HOLD",
            "reason":"FORWARD_ARCHIVE_INTEGRITY_OR_SCHEMA_REJECTED",
            "all_forecast_byte_pins_valid":False,
            "scored_result_count":0,
            "production_recommendations":"DISABLED"
        },sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
