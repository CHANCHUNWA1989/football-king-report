"""One-source, bounded Bundesliga prospective identity A/B data probe.

Reuses the audited OpenLigaDB collector's one no-redirect, exact-URL GET.
No bookmaker requests, no bets, no actual-KO/independent-FT attestations.
The season HTTP body is never exposed as a public GitHub action artifact.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

try:
    from .identity_ab_compare import compare
    from .team_identity import team_id
    from .shadow_raw_source_collector import (
        fetch, source_urls, strict_json_loads, MAX_BYTES)
except ImportError:
    from identity_ab_compare import compare
    from team_identity import team_id
    from shadow_raw_source_collector import fetch, source_urls, strict_json_loads, MAX_BYTES

HK = ZoneInfo("Asia/Hong_Kong")
MAX_SOURCE_MATCHES = 500


class ForwardProbeError(ValueError):
    """Constant, public-safe diagnostic reason only."""


def _require(condition, code):
    if not condition:
        raise ForwardProbeError(code)


def _utc(value):
    _require(type(value) is str and len(value) <= 60, "INVALID_PROVIDER_KICKOFF")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(dt.tzinfo is not None and dt.utcoffset() is not None,
                 "INVALID_PROVIDER_KICKOFF")
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ForwardProbeError("INVALID_PROVIDER_KICKOFF") from None


def _positive_id(value):
    return type(value) is int and 0 < value <= 2**63-1


def normalize(raw, *, year, observed_utc):
    """Historical pre-HK-day scores and upcoming no-score fixtures ONLY."""
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES,
             "INVALID_PROVIDER_BODY")
    _require(type(year) is int and 2000 <= year <= 2100,
             "INVALID_PROVIDER_SEASON")
    now = _utc(observed_utc)
    try:
        matches = strict_json_loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ForwardProbeError("INVALID_PROVIDER_BODY") from None
    _require(type(matches) is list and len(matches) <= MAX_SOURCE_MATCHES,
             "INVALID_PROVIDER_MATCHES")
    today_hk = now.astimezone(HK).date()
    seen, rows = set(), []
    canonical_by_provider_id, provider_id_by_canonical = {}, {}
    counts = {
        "total_source_rows": len(matches),
        "league_season_scoped": 0, "eligible_past_90min_rows": 0,
        "eligible_upcoming_no_score_rows": 0,
        "same_day_result_excluded": 0,
        "out_of_window_or_incomplete_excluded": 0,
    }
    league_ids = set()
    for match in matches:
        _require(type(match) is dict, "INVALID_PROVIDER_MATCH")
        if match.get("leagueShortcut") != "bl1" or match.get("leagueSeason") != year:
            continue
        counts["league_season_scoped"] += 1
        match_id = match.get("matchID")
        home, away = match.get("team1"), match.get("team2")
        _require(_positive_id(match_id)
                 and type(home) is dict and type(away) is dict
                 and _positive_id(home.get("teamId"))
                 and _positive_id(away.get("teamId"))
                 and home["teamId"] != away["teamId"]
                 and type(home.get("teamName")) is str
                 and type(away.get("teamName")) is str
                 and home["teamName"].strip() and away["teamName"].strip()
                 and len(home["teamName"]) < 110 and len(away["teamName"]) < 110
                 and _positive_id(match.get("leagueId")),
                 "INVALID_PROVIDER_FIXTURE_IDENTITY")
        _require(match_id not in seen, "DUPLICATE_NATIVE_FIXTURE_ID")
        seen.add(match_id)
        league_ids.add(match["leagueId"])
        ko = _utc(match.get("matchDateTimeUTC"))
        day = ko.astimezone(HK).date()
        name_home, name_away = home["teamName"].strip(), away["teamName"].strip()
        _require(name_home != name_away, "INVALID_PROVIDER_FIXTURE_IDENTITY")
        for team, name in ((home, name_home), (away, name_away)):
            identity = team_id("bundesliga", name)
            native = team["teamId"]
            _require(identity != "" and
                     canonical_by_provider_id.get(native, identity) == identity
                     and provider_id_by_canonical.get(identity, native) == native,
                     "CONFLICTING_PROVIDER_TEAM_IDENTITY")
            canonical_by_provider_id[native] = identity
            provider_id_by_canonical[identity] = native
        base = {
            "date": day.isoformat(), "home": name_home, "away": name_away,
            "event_id": "openligadb:" + str(match_id),
            "kickoff_utc": ko.isoformat(),
            "schedule_utc_source": "OpenLigaDB_SINGLE_SOURCE_UNAUTHENTICATED",
        }
        finished = match.get("matchIsFinished")
        _require(type(finished) is bool, "INVALID_PROVIDER_FT_FLAG")
        if finished:
            # Earlier historical results (relative to this pre-match HK date)
            # may be training inputs, NEVER actual results for the fresh fixture.
            if day >= today_hk:
                counts["same_day_result_excluded"] += 1
                continue
            results = match.get("matchResults")
            _require(type(results) is list, "INVALID_PROVIDER_RESULTS")
            ft = [r for r in results if type(r) is dict
                  and r.get("resultTypeKind") == "After90Minutes"]
            if len(ft) != 1 or any(type(ft[0].get(key)) is not int
                                  or not 0 <= ft[0][key] <= 20
                                  for key in ("pointsTeam1","pointsTeam2")):
                counts["out_of_window_or_incomplete_excluded"] += 1
                continue
            rows.append({
                **base, "status": "FINISHED",
                "score_ft": [ft[0]["pointsTeam1"],ft[0]["pointsTeam2"]],
            })
            counts["eligible_past_90min_rows"] += 1
            continue
        # Do not call a scheduled fixture a completed result. Already
        # scheduled future fixtures must be beyond the model 10min buffer.
        if (ko <= now+timedelta(minutes=10) or
                day > today_hk+timedelta(days=21) or
                day < today_hk):
            counts["out_of_window_or_incomplete_excluded"] += 1
            continue
        # A feed may carry a provisional HT/current score. Treat it as a
        # contaminated pending fixture rather than feeding model future y.
        results = match.get("matchResults")
        if results not in (None, []):
            counts["out_of_window_or_incomplete_excluded"] += 1
            continue
        rows.append({**base, "status": "SCHEDULED", "score_ft": None})
        counts["eligible_upcoming_no_score_rows"] += 1
    _require(len(league_ids) == 1 and counts["league_season_scoped"] >= 30,
             "INVALID_SINGLE_SOURCE_LEAGUE_ID")
    # Deterministic order even if the remote array is shuffled at the source.
    rows.sort(key=lambda x: (
        x["date"],x["kickoff_utc"],x["event_id"],x["status"],
        x["home"],x["away"]))
    return rows, counts


def probe(*, year, observed_utc, raw, source_commit=None):
    """Compute result-free A/B on one immutable public response payload."""
    source_hash = hashlib.sha256(raw).hexdigest()
    rows, coverage = normalize(raw, year=year, observed_utc=observed_utc)
    comparison = compare(rows, league="bundesliga",
                         as_of_utc=observed_utc, source_commit=source_commit)
    # Retrospective scoring explicitly excludes every fixture's outcome
    # from its own model inputs, and is NEVER prospective certification.
    if __package__:
        from .identity_ab_walkforward import assess
    else:
        from identity_ab_walkforward import assess
    retrospective = assess(rows, observed_utc=observed_utc)
    return {
        "schema": "football-king-openliga-one-source-prospective-ab-v1",
        "status": comparison["status"],
        "provider": "OpenLigaDB",
        "fixed_public_api": source_urls(year)["OpenLigaDB"],
        "raw_source_sha256": source_hash,
        "provider_capture_authenticated": False,
        "90min_score_source_independently_verified": False,
        "sample_pre_match_provenance_independently_authenticated": False,
        "source_coverage": coverage,
        "ab": comparison,
        "retrospective_simulation": retrospective,
        "certified_case_count": 0,
        "prediction_accuracy_improved_proven": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", default=None)
    args = parser.parse_args(argv)
    # The gateway collector makes one bounded public GET with a fixed URL,
    # no redirection, duplicate-key rejection, and no credentials.
    started = datetime.now(timezone.utc)
    year = started.astimezone(HK).year
    if started.astimezone(HK).month < 7:
        year -= 1
    try:
        url = source_urls(year)["OpenLigaDB"]
        raw, status, media, final_url = fetch(url)
        received = datetime.now(timezone.utc)
        _require(received.astimezone(HK).date() ==
                 started.astimezone(HK).date(), "HK_DATE_CHANGED_DURING_GET")
        _require(status == 200 and media == "application/json" and final_url == url,
                 "SOURCE_TRANSPORT_UNSAFE")
        result = probe(year=year, observed_utc=received.isoformat(),
                       raw=raw, source_commit=args.source_commit)
    except (ValueError, KeyError, OSError, TypeError, OverflowError) as exc:
        code = str(exc) if isinstance(exc, ForwardProbeError) else "SOURCE_OR_AB_UNAVAILABLE"
        print(json.dumps({
            "status":"HOLD", "reason":code, "certified_case_count":0,
            "prediction_accuracy_improved_proven":False,
            "production_recommendations":"DISABLED",
        }, sort_keys=True))
        return 1
    # Only research A/B metadata + provider source digest; never raw fixture
    # array, bookmaker prices, keys or final outcome labels in public logs.
    safe = {
        "schema": result["schema"], "status": result["status"],
        "provider": result["provider"], "raw_source_sha256": result["raw_source_sha256"],
        "observed_utc": received.isoformat(),
        "source_coverage": result["source_coverage"],
        "ab_counts": result["ab"]["counts"],
        "home_favourite_concentration_review":
            result["ab"]["home_favourite_cohort_risk"]["by_league"]["bundesliga"],
        "home_concentration_threshold_is_not_calibration": True,
        "ab_input_sha256": result["ab"]["input_canonical_sha256"],
        "retrospective_single_source_unverified_counts":
            result["retrospective_simulation"]["counts"],
        "retrospective_simulated_scores_not_forecasts":
            result["retrospective_simulation"]["summary"],
        "historical_source_available_at_cutoff_authenticated": False,
        "certified_case_count": 0,
        "prediction_accuracy_improved_proven": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }
    print(json.dumps(safe, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
