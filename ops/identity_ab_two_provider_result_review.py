"""Read-only two-provider RESULT-CANDIDATE comparison of 19 frozen forecasts.

OpenLigaDB: exact native event ID + scheduled kickoff + 90min FT claim.
OpenFootball: curated league/team identity + Berlin local date, optional time,
               explicit score.ft only (never infer FT from a 0-0 placeholder).

Two hosts / matching scores DO NOT establish upstream independence, actual
kickoff, governing-body settlement or market edge. Never score predictions.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

try:
    from .identity_ab_ft_candidate_link import link as first_link, CandidateLinkError, YEAR
    from .identity_ab_sealed_archive_audit import (
        _parse, _read, INDEX_KEYS, RECORD_KEYS, MAX_INDEX_BYTES,
        MAX_RECORD_BYTES, ForwardArchiveAuditError,
    )
    from .shadow_raw_source_collector import (
        fetch, source_urls, strict_json_loads, MAX_BYTES,
        allowed_media_types,
    )
    from .team_identity import team_id
    from .identity_ab_forward_seal import _date as parse_utc
except ImportError:
    from identity_ab_ft_candidate_link import link as first_link, CandidateLinkError, YEAR
    from identity_ab_sealed_archive_audit import (
        _parse, _read, INDEX_KEYS, RECORD_KEYS, MAX_INDEX_BYTES,
        MAX_RECORD_BYTES, ForwardArchiveAuditError,
    )
    from shadow_raw_source_collector import (
        fetch, source_urls, strict_json_loads, MAX_BYTES,
        allowed_media_types,
    )
    from team_identity import team_id
    from identity_ab_forward_seal import _date as parse_utc

SCHEMA = "football-king-19-two-provider-result-observation-v1"
BERLIN = ZoneInfo("Europe/Berlin")
MAX_OPENFOOTBALL_MATCHES = 500
SEASON_TITLE = "Deutsche Bundesliga 2026/27"
TWO_SOURCES = ("OpenLigaDB", "OpenFootball")


class TwoProviderError(ValueError):
    """Fail-closed source observation without exposing raw data."""


def _require(ok, reason):
    if not ok:
        raise TwoProviderError(reason)


def _dt(value):
    try:
        return parse_utc(value)
    except (ValueError, TypeError, OverflowError):
        raise TwoProviderError("INVALID_OBSERVATION_CLOCK") from None


def _score(value):
    if type(value) is not dict or "ft" not in value:
        return None
    x = value["ft"]
    if (type(x) is not list or len(x) != 2
            or any(type(v) is not int or v < 0 or v > 30 for v in x)):
        return None
    return list(x)


def _second_index(raw):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,
             "INVALID_SECOND_PROVIDER_BYTES")
    try:
        obj = strict_json_loads(raw)
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise TwoProviderError("INVALID_SECOND_PROVIDER_JSON") from None
    _require(type(obj) is dict and obj.get("name") == SEASON_TITLE
             and type(obj.get("matches")) is list
             and len(obj["matches"]) <= MAX_OPENFOOTBALL_MATCHES,
             "INVALID_SECOND_PROVIDER_LEAGUE_SEASON")
    index = {}
    for game in obj["matches"]:
        _require(type(game) is dict, "INVALID_SECOND_PROVIDER_ROW")
        h, a, date = game.get("team1"), game.get("team2"), game.get("date")
        _require(type(h) is str and type(a) is str
                 and 0 < len(h) < 110 and 0 < len(a) < 110
                 and type(date) is str
                 and re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",date) is not None,
                 "INVALID_SECOND_PROVIDER_IDENTITY")
        try:
            local_day = datetime.strptime(date,"%Y-%m-%d").date()
        except ValueError:
            raise TwoProviderError("INVALID_SECOND_PROVIDER_LOCAL_DATE") from None
        home,away = team_id("bundesliga",h),team_id("bundesliga",a)
        _require(bool(home and away) and home != away,
                 "INVALID_SECOND_PROVIDER_IDENTITY")
        # Keep ALL colliding observations. Duplicates are NOT extra votes.
        key=(home,away,local_day.isoformat())
        index.setdefault(key, []).append(game)
    return index


def compare(directory, first_raw, second_raw, *, observed_utc,
            transport_verified=False):
    """All 19 future-sealed games retained, even when sources absent/conflict."""
    now=_dt(observed_utc)
    _require(type(transport_verified) is bool, "INVALID_TRANSPORT_ASSERTION")
    prior=first_link(directory,first_raw,observed_utc=now.isoformat(),
                     transport_verified=transport_verified)
    _require(prior["sealed_forward_forecast_count"] == 19
             and len(prior["case_states"]) == 19
             and prior["certified_scored_case_count"] == 0,
             "UNTRUSTED_FIRST_SOURCE_REVIEW")
    secondary=_second_index(second_raw)
    root=Path(directory)
    index=_parse(_read(root,"index.json",MAX_INDEX_BYTES),
                 expected=INDEX_KEYS)
    reasons=Counter()
    cases=[]
    by_id={str(x["provider_native_event_id"]):x for x in prior["case_states"]}
    for name in sorted(index["record_sha256"]):
        native=name[:-5]
        _require(native in by_id,"INCOMPLETE_SEALED_COVERAGE")
        sealed=_parse(_read(root,name,MAX_RECORD_BYTES),
                      expected=RECORD_KEYS)
        first=by_id[native]
        ko=_dt(sealed["scheduled_kickoff_utc"])
        local=ko.astimezone(BERLIN)
        key=(team_id("bundesliga",sealed["home"]),
             team_id("bundesliga",sealed["away"]),local.date().isoformat())
        matches=secondary.get(key,[])
        score_openliga=first["single_source_score_candidate"]
        score_openfootball=None
        if now < ko:
            state="PREMATCH_PENDING"
        elif first["result_state"] != "SINGLE_SOURCE_90M_SCORE_CANDIDATE":
            state="FIRST_SOURCE_NOT_ELIGIBLE"
        elif len(matches)==0:
            state="SECOND_SOURCE_MISSING"
        elif len(matches)>1:
            state="SECOND_SOURCE_AMBIGUOUS_MATCH"
        else:
            other=matches[0]
            observed_time=other.get("time")
            if observed_time is not None and (
                    type(observed_time) is not str
                    or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]",
                                    observed_time) is None
                    or observed_time != local.strftime("%H:%M")):
                state="SECOND_SOURCE_SCHEDULE_TIME_CONFLICT"
            else:
                score_openfootball=_score(other.get("score"))
                if score_openfootball is None:
                    state="SECOND_SOURCE_NO_EXPLICIT_FT"
                elif score_openliga != score_openfootball:
                    state="TWO_PROVIDER_90M_SCORE_CONFLICT"
                else:
                    state="TWO_PROVIDER_90M_SCORE_AGREEMENT_CANDIDATE"
        reasons[state]+=1
        cases.append({
            "provider_native_event_id":native,
            "sealed_forecast_sha256":index["record_sha256"][name],
            "sealed_scheduled_kickoff_utc":ko.isoformat(),
            "first_provider_state":first["result_state"],
            "second_provider_matched_fixture_count":len(matches),
            "first_source_90m_score":score_openliga,
            "second_source_explicit_ft_score":score_openfootball,
            "comparison_state":state,
            "publisher_upstream_independence_authenticated":False,
            "actual_kickoff_authenticated":False,
            "independent_regulation_ft_authenticated":False,
            "model_scoring_eligible":False,
        })
    _require(len(cases)==19 and sum(reasons.values())==19,
             "INCOMPLETE_19_FORECAST_DENOMINATOR")
    return {
        "schema":SCHEMA,"status":"HOLD",
        "observed_utc":now.isoformat(),
        "provider_names":list(TWO_SOURCES),
        "source_hashes_sha256":{
            "OpenLigaDB":hashlib.sha256(first_raw).hexdigest(),
            "OpenFootball":hashlib.sha256(second_raw).hexdigest(),
        },
        "transport_observed_not_authenticated":transport_verified,
        "original_forecast_count":19,
        "case_state_counts":dict(sorted(reasons.items())),
        "two_provider_matching_score_candidates":
            reasons["TWO_PROVIDER_90M_SCORE_AGREEMENT_CANDIDATE"],
        "two_provider_conflicting_score_candidates":
            reasons["TWO_PROVIDER_90M_SCORE_CONFLICT"],
        "per_fixture":cases,
        "actual_kickoff_authenticated":False,
        "upstream_independence_authenticated":False,
        "independently_verified_regulation_ft":0,
        "certified_scored_cases":0,
        "model_accuracy_improved_proven":False,
        "positive_ev_verified":False,
        "production_recommendations":"DISABLED",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        urls=source_urls(YEAR)
        source={}
        for provider in TWO_SOURCES:
            url=urls[provider]
            raw,status,media,final_url=fetch(url)
            _require(status==200 and final_url==url
                     and media in allowed_media_types(provider),
                     "UNSAFE_PROVIDER_TRANSPORT")
            source[provider]=raw
        now=datetime.now(timezone.utc)
        report=compare(args.directory,
                       source["OpenLigaDB"],source["OpenFootball"],
                       observed_utc=now.isoformat(),transport_verified=True)
        print(json.dumps({
            "status":"HOLD","schema":SCHEMA,
            "original_forecasts":report["original_forecast_count"],
            "source_hashes_sha256":report["source_hashes_sha256"],
            "states":report["case_state_counts"],
            "two_provider_score_agreements":
                report["two_provider_matching_score_candidates"],
            "two_provider_score_conflicts":
                report["two_provider_conflicting_score_candidates"],
            "upstream_independence_authenticated":False,
            "official_ft_authenticated":False,
            "certified_scored_cases":0,
            "production_recommendations":"DISABLED",
        },sort_keys=True))
        return 0
    except (TwoProviderError,CandidateLinkError,ForwardArchiveAuditError,
            ValueError,KeyError,TypeError,OSError,OverflowError):
        print(json.dumps({
            "status":"HOLD","reason":"SECOND_SOURCE_CANDIDATE_CHECK_UNAVAILABLE",
            "original_forecasts_expected":19,"certified_scored_cases":0,
            "production_recommendations":"DISABLED",
        },sort_keys=True))
        return 1


if __name__=="__main__":
    raise SystemExit(main())
