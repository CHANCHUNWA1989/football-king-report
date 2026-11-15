"""One real, already-fetched, public OpenLigaDB result-original smoke.

Only compares a local 2026-11-15 HTTP response to its **observed**
SHA-256. Never fetches, republishes, independently attests TLS/publisher
identity, certifies an archived forecast or promotes a betting model.

Official German license: https://www.openligadb.de/lizenz
Official German API terms: https://www.openligadb.de/nutzungsbedingungen
ODbL 1.0 permits commercial *data use* under conditions, but independent
source/authorship, API terms, legal obligations and truth remain distinct.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import argparse
import json
import os
import stat
import sys

SCHEMA = "football-king-vnext-openligadb-historical-original-v1"
SOURCE_URL = "https://api.openligadb.de/getmatchdata/83156"
PROVIDER_LICENSE_URL = "https://www.openligadb.de/lizenz"
PROVIDER_TERMS_URL = "https://www.openligadb.de/nutzungsbedingungen"
MATCH_ID = 83156
EXPECTED_KICKOFF = "2026-08-28T18:30:00Z"
HOME_TEAM_ID = 40
AWAY_TEAM_ID = 16
OFFICIAL_BYTES = 2508
OFFICIAL_JSON_SHA256 = "420aca223bdc71d3a5f88a0af8d76c54406567a296934a40bab313800b3e0e2d"
OBSERVED_HTTP_DATE = "Sun, 15 Nov 2026 07:50:50 GMT"
OBSERVED_RUNNER_UTC = "2026-11-15T07:50:50.323115+00:00"
MAX_SOURCE_BYTES = 2_000_000


def _unique_json_keys(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("DUPLICATE_RESULT_JSON_KEY")
        result[name] = value
    return result


def _nonfinite_result_number(value):
    raise ValueError("NONFINITE_RESULT_JSON")


def _parse_structured_result(raw):
    """Parse a provider JSON original; fixture and 90-minute score only.

    This only checks structural claims in the bytes, never their truth.
    A URL, provider label or input JSON cannot grant authorization.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_SOURCE_BYTES:
        raise ValueError("UNSAFE_PROVIDER_JSON_SIZE")
    try:
        obj = json.loads(raw, object_pairs_hook=_unique_json_keys,
                         parse_constant=_nonfinite_result_number)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("INVALID_PROVIDER_RESULT_JSON") from exc
    if type(obj) is not dict:
        raise ValueError("INVALID_PROVIDER_RESULT_STRUCTURE")
    if type(obj.get("matchID")) is not int or obj["matchID"] != MATCH_ID:
        raise ValueError("MISMATCHED_PROVIDER_FIXTURE_ID")
    if obj.get("matchIsFinished") is not True:
        raise ValueError("UNFINISHED_PROVIDER_MATCH")
    team1, team2 = obj.get("team1"), obj.get("team2")
    if (type(team1) is not dict or type(team2) is not dict
            or type(team1.get("teamId")) is not int
            or type(team2.get("teamId")) is not int
            or team1["teamId"] != HOME_TEAM_ID
            or team2["teamId"] != AWAY_TEAM_ID
            or obj.get("leagueShortcut") != "bl1"
            or type(obj.get("leagueSeason")) is not int
            or obj["leagueSeason"] != 2026
            or obj.get("matchDateTimeUTC") != EXPECTED_KICKOFF):
        raise ValueError("MISMATCHED_PROVIDER_FIXTURE")
    candidates = obj.get("matchResults")
    if type(candidates) is not list:
        raise ValueError("MISSING_UNIQUE_90MIN_RESULT")
    finals = [row for row in candidates
              if type(row) is dict and row.get("resultTypeKind") == "After90Minutes"]
    if len(finals) != 1:
        raise ValueError("MISSING_UNIQUE_90MIN_RESULT")
    home, away = finals[0].get("pointsTeam1"), finals[0].get("pointsTeam2")
    if (type(home) is not int or type(away) is not int
            or not 0 <= home <= 30 or not 0 <= away <= 30):
        raise ValueError("INVALID_PROVIDER_90MIN_SCORE")
    return {
        "fixture_id": "OpenLigaDB:83156",
        "provider_fixture_id": MATCH_ID,
        "home_team_id": HOME_TEAM_ID,
        "away_team_id": AWAY_TEAM_ID,
        "kickoff_utc_as_claimed_by_provider": EXPECTED_KICKOFF,
        "home_goals": home, "away_goals": away,
        "result_type_kind": "After90Minutes",
        "match_is_finished_asserted_by_provider": True,
    }


def _read_source(path):
    if not isinstance(path, (Path, str)):
        raise ValueError("UNSAFE_RESULT_ORIGINAL_PATH")
    file = Path(path)
    if any(p.is_symlink() for p in (file, *file.parents)):
        raise ValueError("UNSAFE_RESULT_ORIGINAL_PATH")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(file, flags)
    except OSError as exc:
        raise ValueError("OFFICIAL_RESULT_ORIGINAL_BYTES_NOT_PRESENT_OR_CHANGED") from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_nlink != 1:
            raise ValueError("UNSAFE_RESULT_ORIGINAL_PATH")
        if file_stat.st_size != OFFICIAL_BYTES:
            raise ValueError("OFFICIAL_RESULT_ORIGINAL_BYTES_NOT_PRESENT_OR_CHANGED")
        chunks = []
        read_count = 0
        while read_count <= MAX_SOURCE_BYTES:
            chunk = os.read(fd, min(65536, MAX_SOURCE_BYTES + 1 - read_count))
            if not chunk:
                break
            read_count += len(chunk)
            chunks.append(chunk)
        raw = b"".join(chunks)
        if len(raw) != OFFICIAL_BYTES:
            raise ValueError("OFFICIAL_RESULT_ORIGINAL_BYTES_NOT_PRESENT_OR_CHANGED")
        return raw
    finally:
        os.close(fd)


def _result_hold(reason, **extra):
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": reason,
        "provider": "OpenLigaDB",
        "source_url_as_requested": SOURCE_URL,
        "provider_license_url": PROVIDER_LICENSE_URL,
        "provider_terms_url": PROVIDER_TERMS_URL,
        "source_original_sha256_verified": False,
        "publisher_identity_independently_verified": False,
        "capture_time_independently_attested": False,
        "provider_independence_from_other_results_authenticated": False,
        "actual_kickoff_independently_verified": False,
        "result_truth_verified": False,
        "commercial_licence_fully_cleared_for_deployment": False,
        "external_witness_independently_verified": False,
        "eligible_for_model_scoring": False,
        "certified_prospective_samples": 0,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
        **extra,
    }


def review_historical_original(path):
    """Inspect an exact offline response. A valid result STILL returns HOLD."""
    try:
        data = _read_source(path)
        if sha256(data).hexdigest() != OFFICIAL_JSON_SHA256:
            raise ValueError("OFFICIAL_RESULT_ORIGINAL_BYTES_NOT_PRESENT_OR_CHANGED")
        result = _parse_structured_result(data)
        if (result["home_goals"], result["away_goals"]) != (5, 1):
            raise ValueError("OFFICIAL_RESULT_SCORE_CHANGED")
        # Two time values are *observed headers/runner claims*, not
        # independent source-signed time attestations. Basic sanity only.
        capture = datetime.fromisoformat(OBSERVED_RUNNER_UTC)
        header = datetime.strptime(OBSERVED_HTTP_DATE,
                                   "%a, %d %b %Y %H:%M:%S GMT").replace(
                                       tzinfo=timezone.utc)
        kickoff = datetime.fromisoformat(EXPECTED_KICKOFF.replace("Z", "+00:00"))
        if not (kickoff + timedelta(minutes=90) <= header
                <= capture <= header + timedelta(minutes=5)):
            raise ValueError("UNTRUSTED_CAPTURE_TIME_RELATIONSHIP")
        return _result_hold(
            "SOURCE_BYTES_MATCH_CAPTURED_HISTORICAL_RESPONSE_BUT_UNATTESTED",
            source_original_sha256_verified=True,
            raw_source_sha256=OFFICIAL_JSON_SHA256,
            raw_source_bytes=OFFICIAL_BYTES,
            observed_response_http_date_unattested=OBSERVED_HTTP_DATE,
            runner_capture_utc_unattested=OBSERVED_RUNNER_UTC,
            result_90min_claimed_by_provider={
                "home_goals": result["home_goals"],
                "away_goals": result["away_goals"],
            },
            fixture_id=result["fixture_id"],
            historical_provider_response_only=True,
        )
    except (ValueError, OSError, TypeError, UnicodeError) as exc:
        return _result_hold(
            str(exc) if isinstance(exc, ValueError) and len(str(exc)) < 120
            else "OFFICIAL_RESULT_ORIGINAL_BYTES_NOT_PRESENT_OR_CHANGED")


def main(argv=None):
    cli = argparse.ArgumentParser(description="Read-only offline OpenLigaDB result byte smoke")
    cli.add_argument("--original", required=True)
    args = cli.parse_args(argv)
    result = review_historical_original(args.original)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["source_original_sha256_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
