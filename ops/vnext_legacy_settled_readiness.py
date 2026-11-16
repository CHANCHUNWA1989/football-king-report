"""Read-only legacy 1X2 settled archive provenance readiness gate.

A Git blob checksum authenticates *only the supplied bytes relative to a
separately supplied Git blob reference*. It does not prove provider identity,
source truth, record capture time or model correctness. This audit never
certifies prospective performance, independently verified final results,
commercial rights, profitability, positive EV or automated wagering.

This module does NOT replace PR #451's descriptive Brier/log-loss audit.
It reports only structural missing provenance and refuses caller flags as
evidence. No provider HTTP requests, data imports, settlements or bets.
"""
import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha1
import json
import math
from pathlib import Path
import re
import sys

SCHEMA = "football-king-vnext-legacy-settled-readiness-v1"
MAX_ARCHIVE_BYTES = 8_000_000
MAX_ROWS = 20_000
GIT_BLOB_SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _uniquely_named_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_ARCHIVE_JSON_KEY")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ValueError("NONFINITE_ARCHIVE_JSON_NUMBER")


def _clock(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_ARCHIVE_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_ARCHIVE_TIMESTAMP") from None
    if stamp.utcoffset() is None:
        raise ValueError("NAIVE_ARCHIVE_TIMESTAMP")
    return stamp


def _probability_vector(value):
    if (type(value) is not list or len(value) != 3
            or any(type(x) not in (float, int) or not math.isfinite(x)
                   or x < 0 or x > 1 for x in value)
            or abs(math.fsum(value) - 1) > .002):
        raise ValueError("INVALID_ARCHIVED_PROBABILITIES")


def _valid_sha256(value):
    return type(value) is str and SHA256.fullmatch(value) is not None


def _present(value):
    return type(value) is str and bool(value.strip())


def _fixture_binding(value):
    return (type(value) is dict
            and _present(value.get("provider"))
            and (type(value.get("match_id")) is str
                 and bool(value["match_id"].strip())))


def audit_archive_bytes(raw, *, expected_git_blob_sha1):
    """Check a fixed input archive; output only unverified readiness counts.

    IMPORTANT: the caller must obtain expected_git_blob_sha1 independently
    from the trusted repository. A matching SHA1 is not a publisher signature.
    A returned HOLD stays HOLD even if sample flags assert verification.
    """
    if (type(expected_git_blob_sha1) is not str
            or GIT_BLOB_SHA1.fullmatch(expected_git_blob_sha1) is None):
        raise ValueError("INVALID_EXTERNAL_GIT_BLOB_REFERENCE")
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_ARCHIVE_BYTES:
        raise ValueError("MISSING_OR_OVERSIZED_ARCHIVE_BYTES")
    actual = sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if actual != expected_git_blob_sha1:
        raise ValueError("ARCHIVE_GIT_BLOB_MISMATCH")
    try:
        record = json.loads(raw, object_pairs_hook=_uniquely_named_object,
                            parse_constant=_reject_nonfinite)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("INVALID_ARCHIVE_JSON") from exc
    if type(record) is not dict:
        raise ValueError("INVALID_ARCHIVE_SCHEMA")
    if record.get("production_recommendations") != "DISABLED":
        raise ValueError("UNSAFE_ARCHIVE_TOP_LEVEL_PROMOTION")
    rows = record.get("samples")
    if type(rows) is not list or len(rows) > MAX_ROWS:
        raise ValueError("INVALID_ARCHIVE_SAMPLES")
    # A checked-at self-claim is never evidence that archived data existed
    # at that instant. Parse for structure but do not certify provenance.
    _clock(record.get("checked_utc"))

    coverage = Counter({
        "fixture_identity": 0,
        "forecast_event_id": 0,
        "model_artifact_digest": 0,
        "result_source_reference": 0,
        "result_original_digest": 0,
        "asserted_result_independence": 0,
    })
    suspicious = 0
    fixtures = set()
    leagues = Counter()
    for row in rows:
        if type(row) is not dict or row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_ARCHIVE_ROW_PROMOTION")
        key = row.get("key")
        if not _present(key) or len(key) > 2000:
            raise ValueError("INVALID_ARCHIVED_FIXTURE_KEY")
        if key in fixtures:
            raise ValueError("DUPLICATE_ARCHIVED_FIXTURE_KEY")
        fixtures.add(key)
        market = _clock(row.get("market_utc"))
        forecast = _clock(row.get("forecast_utc"))
        kickoff = _clock(row.get("kickoff_utc"))
        if not market <= forecast < kickoff:
            raise ValueError("INVALID_ARCHIVED_CHRONOLOGY")
        if type(row.get("y")) is not int or row["y"] not in (0, 1, 2):
            raise ValueError("INVALID_ARCHIVED_OUTCOME")
        _probability_vector(row.get("p"))
        _probability_vector(row.get("m"))
        if not _present(row.get("league")):
            raise ValueError("INVALID_ARCHIVED_LEAGUE")
        leagues[row["league"]] += 1

        coverage["fixture_identity"] += int(_fixture_binding(row.get("source_fixture_identity")))
        coverage["forecast_event_id"] += int(_present(row.get("forecast_event_id")))
        coverage["model_artifact_digest"] += int(_valid_sha256(row.get("model_artifact_sha256")))
        coverage["result_source_reference"] += int(_present(row.get("fixture_result_source")))
        coverage["result_original_digest"] += int(
            _valid_sha256(row.get("source_raw_sha256"))
            or _valid_sha256(row.get("fixture_result_source_raw_sha256")))
        coverage["asserted_result_independence"] += int(
            row.get("fixture_result_source_independently_verified") is True)
        suspicious += int(any(row.get(field) is True for field in (
            "fixture_result_source_independently_verified",
            "independently_verified", "eligible_for_model_scoring",
            "external_forecast_witness_verified",
            "positive_ev_verified", "production_recommendation_allowed",
        )))

    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "archive_git_blob_sha1_matches_supplied_reference": True,
        "archive_git_blob_sha1": actual,
        "source_repo_and_commit_externally_attested": False,
        "source_publisher_identity_independently_verified": False,
        "archived_rows": len(rows),
        "structurally_checked_rows": len(rows),
        "leagues": dict(sorted(leagues.items())),
        "field_coverage": dict(coverage),
        "unsupported_certification_claim_rows": suspicious,
        "top_level_independent_results_claim": record.get("results_independently_verified") is True,
        "top_level_profitability_claim": record.get("profitability_verified") is True,
        "missing_external_forecast_proof_rows": len(rows),
        "missing_independent_result_original_rows": len(rows),
        "external_witness_independently_verified": False,
        "result_source_identity_independently_verified": False,
        "licensed_original_bytes_independently_verified": False,
        "commercial_data_rights_verified": False,
        "certified_prospective_rows": 0,
        "predictive_accuracy_gain_verified": False,
        "positive_ev_verified": False,
        "profitability_verified": False,
        "production_recommendations": "DISABLED",
        "note": (
            "Structural field counts, not externally authenticated source capture. "
            "Matching Git blob identity and self-reported validation flags do not "
            "authenticate provider result originals, match truth or pre-match sealing."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="HOLD-only settled evidence readiness audit")
    parser.add_argument("--archive", required=True, help="Local archive bytes, never uploaded")
    parser.add_argument("--expected-git-blob-sha1", required=True,
                        help="Git blob SHA1 independently obtained from exact repository revision")
    args = parser.parse_args(argv)
    try:
        archive = Path(args.archive)
        if archive.is_symlink() or not archive.is_file() or archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("UNSAFE_ARCHIVE_PATH")
        output = audit_archive_bytes(archive.read_bytes(),
                                     expected_git_blob_sha1=args.expected_git_blob_sha1)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "HOLD", "production_recommendations": "DISABLED",
                          "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
