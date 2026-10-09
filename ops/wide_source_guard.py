"""Reject false current-season coverage, fabricated market odds or unsafe raw data."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from wide_sources import (NOW_LEAGUES, HISTORY_LEAGUES, GERMAN_LEAGUES,
                          PROVIDER_NAMES, MAX_EXAMPLES, MAX_REQUESTS,
                          SCHEMA, utc_clock)
EXPECTED = [(a, c, "openfootball_json", "CURRENT_SEASON_FILE")
            for a,_,c in NOW_LEAGUES]
EXPECTED += [(a,c,"openfootball_json","ARCHIVED_SEASON_ONLY")
             for a,_,c in HISTORY_LEAGUES]
EXPECTED += [(a,None,"openligadb","2026_SEASON_REQUEST_NOT_FRESHNESS_PROOF")
             for a,_,_ in GERMAN_LEAGUES]
SAFETY = ("market_odds_available", "automatic_prediction_training",
          "results_independently_verified")


def verify(doc, *, clock=None):
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError("INVALID_WIDE_SCHEMA")
    if (doc.get("production_recommendations") != "DISABLED"
            or doc.get("status") != "RESEARCH_ONLY"
            or doc.get("historic_openfootball_season_is_not_live") is not True
            or doc.get("timezone_of_openfootball_match_time_unconfirmed") is not True
            or any(doc.get(key) is not False for key in SAFETY)):
        raise ValueError("INVALID_WIDE_PROVENANCE")
    current = utc_clock(doc.get("collected_utc"))
    now = clock or datetime.now(timezone.utc)
    if abs((now-current).total_seconds()) > 7*86400:
        raise ValueError("WIDE_SNAPSHOT_TIME_UNREASONABLE")
    runs = doc.get("league_coverage")
    providers = doc.get("providers")
    if (not isinstance(runs, list) or len(runs) != MAX_REQUESTS
            or doc.get("league_file_total") != MAX_REQUESTS
            or not isinstance(providers, list)
            or [p.get("provider") for p in providers if isinstance(p, dict)]
               != list(PROVIDER_NAMES)):
        raise ValueError("INVALID_WIDE_LEAGUE_COUNT")
    samples = doc.get("source_samples")
    if not isinstance(samples, list) or len(samples) > MAX_EXAMPLES:
        raise ValueError("INVALID_SAMPLE_COUNT")
    if (type(doc.get("provider_calls_attempted")) is not int or
            not 0 <= doc["provider_calls_attempted"] <= MAX_REQUESTS or
            doc.get("provider_call_budget") != MAX_REQUESTS):
        raise ValueError("WIDE_REQUEST_CAP_BROKEN")
    observed_files = 0
    current_files = 0
    archived_files = 0
    for pos, (row, definition) in enumerate(zip(runs, EXPECTED)):
        league, source_path, provider, season_class = definition
        if (not isinstance(row, dict) or row.get("league") != league
                or row.get("provider") != provider
                or row.get("usable_for_live_betting") is not False
                or row.get("access_status") not in (
                    "FETCHED", "NO_FILE_OR_ACCESS", "RATE_LIMITED", "NETWORK_ERROR",
                    "INVALID_SCHEMA_OR_RESPONSE", "TIME_BUDGET_EXHAUSTED", "HTTP_ERROR")):
            raise ValueError("INVALID_WIDE_LEAGUE_DETAILS")
        if provider == "openfootball_json" and (
                row.get("season_scope") not in (
                    "CURRENT_SEASON_FILE", "ARCHIVED_SEASON_ONLY", "CURRENT_SEASON", "ARCHIVE")
                or (row["access_status"] == "FETCHED" and
                    (row.get("dataset_path") != source_path or
                     row.get("season_scope") != season_class))):
            raise ValueError("MISLABELED_HISTORICAL_SEASON")
        if row["access_status"] == "FETCHED":
            observed_files += 1
            if row.get("season_scope") == "CURRENT_SEASON_FILE":
                current_files += 1
            if row.get("season_scope") == "ARCHIVED_SEASON_ONLY":
                archived_files += 1
            if (type(row.get("records")) is not int or row["records"] < 0 or
                    type(row.get("reported_ft_scores_unverified")) is not int or
                    row["reported_ft_scores_unverified"] < 0 or
                    row["reported_ft_scores_unverified"] > row["records"]):
                raise ValueError("INVALID_WIDE_SCORE_COUNTS")
            if provider == "openfootball_json" and row.get("precise_utc_kickoffs_confirmed") != 0:
                raise ValueError("OPENFOOTBALL_UNZONED_CLOCK_FALSE_CLAIM")
    if (doc.get("successful_league_files") != observed_files or
            doc.get("current_season_file_successes") != current_files or
            doc.get("historical_only_file_successes") != archived_files):
        raise ValueError("FALSE_WIDE_FILE_COUNTS")
    if any(p.get("production_recommendations") != "DISABLED" or
           p.get("odds_market_fallback_available") is not False or
           p.get("requires_key") is not False or
           p.get("configured") is not True
           for p in providers):
        raise ValueError("UNSAFE_WIDE_PROVIDER")
    for row in samples:
        if (not isinstance(row, dict) or
                row.get("production_recommendations") != "DISABLED" or
                row.get("source") not in PROVIDER_NAMES or
                row.get("league") not in {item[0] for item in EXPECTED} or
                not isinstance(row.get("home"), str) or
                not isinstance(row.get("away"), str) or
                not isinstance(row.get("score_full_time"), (list, type(None)))):
            raise ValueError("INVALID_WIDE_SAMPLE")
        if row["source"] == "openfootball_json" and (
                row.get("kickoff_utc") is not None or
                "calendar_date_only" not in row):
            raise ValueError("OPENFOOTBALL_TIMEZONE_NOT_VERIFIED")
        if row["source"] == "openligadb":
            utc_clock(row["kickoff_utc"])
    return current


def newer(new, old):
    moment = verify(new)
    if old is None:
        return True
    previous = verify(old)
    if previous == moment and old != new:
        raise ValueError("SAME_TIME_WIDE_SNAPSHOT_CONFLICT")
    return moment > previous


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--incoming", required=True)
    p.add_argument("--previous", default="")
    args = p.parse_args()
    latest = json.loads(Path(args.incoming).read_text(encoding="utf-8"))
    prior = json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous and Path(args.previous).is_file() else None
    print(json.dumps({"safe_to_publish": newer(latest, prior),
                      "provider_count": len(latest["providers"]),
                      "leagues": len(latest["league_coverage"]),
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
