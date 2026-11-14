"""Unverified FT candidate linkage to first 19 GitHub-sealed pre-match forecasts.

One *current* OpenLigaDB result observation can be compared by the exact native
match ID, league, canonical home/away teams and frozen scheduled kickoff. It
never authenticates actual kickoff, the publisher, independent FT, or results.
No Brier/log loss, betting advice, settlement ledger writes, or cherry-picking.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

try:
    from .identity_ab_sealed_archive_audit import (
        RUN_DIRECTORY, PINNED_INDEX_GIT_BLOB_SHA1, INDEX_KEYS, RECORD_KEYS,
        _parse, _read, audit as audit_seal, ForwardArchiveAuditError,
        MAX_INDEX_BYTES, MAX_RECORD_BYTES,
    )
    from .shadow_raw_source_collector import (
        fetch, source_urls, strict_json_loads, MAX_BYTES,
    )
    from .team_identity import team_id
    from .identity_ab_forward_seal import _date as parse_utc
except ImportError:
    from identity_ab_sealed_archive_audit import (
        RUN_DIRECTORY, PINNED_INDEX_GIT_BLOB_SHA1, INDEX_KEYS, RECORD_KEYS,
        _parse, _read, audit as audit_seal, ForwardArchiveAuditError,
        MAX_INDEX_BYTES, MAX_RECORD_BYTES,
    )
    from shadow_raw_source_collector import fetch, source_urls, strict_json_loads, MAX_BYTES
    from team_identity import team_id
    from identity_ab_forward_seal import _date as parse_utc

SCHEMA = "football-king-forward-19-single-source-ft-candidate-link-v1"
MAX_MATCHES = 500
YEAR = 2026
CANDIDATE_POST_KICKOFF_BUFFER = timedelta(hours=3)


class CandidateLinkError(ValueError):
    """Fixed diagnostic error code, no third-party body or credentials."""


def _require(ok, reason):
    if not ok:
        raise CandidateLinkError(reason)


def _stamp(value):
    try:
        return parse_utc(value)
    except (ValueError, TypeError, OverflowError):
        raise CandidateLinkError("INVALID_PROVIDER_OR_AUDIT_CLOCK") from None


def _positive_int(value):
    return type(value) is int and 0 < value <= 2**63-1


def _score90(value):
    """Exact one After90Minutes result; not full-time status by itself."""
    if type(value) is not list:
        return None
    matches = [x for x in value if type(x) is dict
               and x.get("resultTypeKind") == "After90Minutes"]
    if len(matches) != 1:
        return None
    home, away = matches[0].get("pointsTeam1"), matches[0].get("pointsTeam2")
    if type(home) is not int or type(away) is not int:
        return None
    if not 0 <= home <= 30 or not 0 <= away <= 30:
        return None
    return [home, away]


def link(directory, raw, *, observed_utc, transport_verified=False):
    """Return all 19 states in original sealed denominator; never score."""
    now = _stamp(observed_utc)
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,
             "INVALID_RESULT_SOURCE_BODY")
    _require(type(transport_verified) is bool, "INVALID_TRANSPORT_RECEIPT")
    try:
        snapshot = strict_json_loads(raw)
    except (UnicodeError, ValueError, TypeError, RecursionError):
        raise CandidateLinkError("INVALID_RESULT_SOURCE_JSON") from None
    _require(type(snapshot) is list and len(snapshot) <= MAX_MATCHES,
             "INVALID_RESULT_SOURCE_SHAPE")
    archive = Path(directory)
    verified = audit_seal(archive, as_of_utc=now.isoformat())
    _require(verified["forecast_file_count"] == 19
             and verified["all_forecast_byte_pins_valid"] is True,
             "FORECAST_ARCHIVE_NOT_COMPLETE")
    index = _parse(_read(archive, "index.json", MAX_INDEX_BYTES),
                   expected=INDEX_KEYS)
    _require(index["record_count"] == 19,
             "FORECAST_ARCHIVE_NOT_COMPLETE")
    cases = {}
    for name in sorted(index["record_sha256"]):
        row = _parse(_read(archive, name, MAX_RECORD_BYTES),
                     expected=RECORD_KEYS)
        _require(row["provider_native_event_id"] == name[:-5],
                 "SEALED_NATIVE_ID_CONFLICT")
        cases[int(name[:-5])] = row
    # Match ONLY native IDs that already existed in the sealed archive.
    # No fallback by team-name similarity or result score.
    matches = {}
    for obj in snapshot:
        _require(type(obj) is dict, "INVALID_RESULT_SOURCE_MATCH")
        native = obj.get("matchID")
        if type(native) is not int or native not in cases:
            continue
        _require(native not in matches, "DUPLICATE_NATIVE_RESULT_MATCH")
        matches[native] = obj
    reasons = Counter()
    details = []
    for native, row in sorted(cases.items()):
        ko = _stamp(row["scheduled_kickoff_utc"])
        expected_home = team_id("bundesliga", row["home"])
        expected_away = team_id("bundesliga", row["away"])
        _require(bool(expected_home and expected_away)
                 and expected_home != expected_away,
                 "SEALED_CLUB_IDENTITY_UNSAFE")
        source = matches.get(native)
        score = None
        if now < ko:
            state = "PREMATCH_PENDING"
            # A source asserting completion before the scheduled kickoff
            # isn't allowed to masquerade as valid FT evidence.
            if source is not None and source.get("matchIsFinished") is True:
                state = "SOURCE_FT_BEFORE_SEALED_KICKOFF_HOLD"
        elif source is None:
            state = "NATIVE_RESULT_NOT_FOUND"
        elif (source.get("leagueShortcut") != "bl1"
              or source.get("leagueSeason") != YEAR
              or not _positive_int(source.get("leagueId"))
              or type(source.get("team1")) is not dict
              or type(source.get("team2")) is not dict
              or not _positive_int(source["team1"].get("teamId"))
              or not _positive_int(source["team2"].get("teamId"))
              or source["team1"]["teamId"] == source["team2"]["teamId"]
              or team_id("bundesliga", source["team1"].get("teamName"))
                 != expected_home
              or team_id("bundesliga", source["team2"].get("teamName"))
                 != expected_away):
            state = "NATIVE_ID_OR_CLUB_IDENTITY_CONFLICT_HOLD"
        else:
            try:
                source_ko = _stamp(source.get("matchDateTimeUTC"))
            except CandidateLinkError:
                source_ko = None
            if source_ko != ko:
                state = "SCHEDULED_KICKOFF_CHANGED_HOLD"
            elif type(source.get("matchIsFinished")) is not bool:
                state = "INVALID_FINAL_STATUS_HOLD"
            elif source["matchIsFinished"] is False:
                state = "NOT_REPORTED_FINISHED"
            elif now < ko + CANDIDATE_POST_KICKOFF_BUFFER:
                state = "CANDIDATE_TOO_EARLY_AFTER_SCHEDULED_KICKOFF_HOLD"
            else:
                score = _score90(source.get("matchResults"))
                state = ("SINGLE_SOURCE_90M_SCORE_CANDIDATE" if score is not None
                         else "MISSING_OR_AMBIGUOUS_90M_RESULT_HOLD")
        reasons[state] += 1
        details.append({
            "provider_native_event_id":str(native),
            "sealed_scheduled_kickoff_utc":ko.isoformat(),
            "sealed_forecast_sha256":index["record_sha256"][str(native)+".json"],
            "result_state":state, "single_source_score_candidate":score,
            "independent_upstream_authenticated":False,
            "actual_kickoff_authenticated":False,
            "regulation_ft_independently_authenticated":False,
            "model_scoring_eligible":False,
        })
    _require(len(details) == len(cases) == 19
             and sum(reasons.values()) == 19,
             "INCOMPLETE_RESULT_REVIEW_DENOMINATOR")
    return {
        "schema":SCHEMA, "status":"HOLD",
        "provider":"OpenLigaDB",
        "observed_utc":now.isoformat(),
        "result_source_sha256":hashlib.sha256(raw).hexdigest(),
        "bounded_single_source_transport_checked":transport_verified,
        "sealed_original_index_git_blob_sha1":PINNED_INDEX_GIT_BLOB_SHA1,
        "sealed_forward_forecast_count":19,
        "case_states":details,
        "case_state_counts":dict(sorted(reasons.items())),
        "one_source_90m_score_candidate_count":
            reasons["SINGLE_SOURCE_90M_SCORE_CANDIDATE"],
        "matched_native_id_count":len(matches),
        "independently_verified_ft_count":0,
        "certified_scored_case_count":0,
        "model_accuracy_uplift_proven":False,
        "positive_ev_verified":False,
        "production_recommendations":"DISABLED",
        "warning":"SOURCE_CANDIDATES_NOT_INDEPENDENT_REGULATION_FT",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        url=source_urls(YEAR)["OpenLigaDB"]
        body,status,media,final_url=fetch(url)
        observed=datetime.now(timezone.utc).isoformat()
        _require(status == 200 and final_url == url and media == "application/json",
                 "RESULT_SOURCE_TRANSPORT_UNSAFE")
        report=link(args.directory,body,observed_utc=observed,
                    transport_verified=True)
        # Public logs only counts and digest, never outcome candidates.
        print(json.dumps({
            "status":report["status"],"schema":report["schema"],
            "source_sha256":report["result_source_sha256"],
            "observed_utc":report["observed_utc"],
            "sealed_forecasts":report["sealed_forward_forecast_count"],
            "states":report["case_state_counts"],
            "source_ft_candidates":
                report["one_source_90m_score_candidate_count"],
            "independently_verified_results":0,
            "certified_scored_cases":0,
            "model_accuracy_uplift_proven":False,
            "production_recommendations":"DISABLED",
        },sort_keys=True))
        return 0
    except (CandidateLinkError, ForwardArchiveAuditError, OSError, ValueError,
            TypeError, OverflowError, KeyError):
        print(json.dumps({"status":"HOLD",
                          "reason":"RESULT_CANDIDATE_LINKAGE_REJECTED",
                          "sealed_forecasts_expected":19,
                          "independently_verified_results":0,
                          "certified_scored_cases":0,
                          "production_recommendations":"DISABLED"},sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
