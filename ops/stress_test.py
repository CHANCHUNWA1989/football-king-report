"""Deterministic, offline Football King load/stress testing.

No network, no credentials, no betting, no provider budget expenditure.
Generated matches are synthetic and never published as live observations.
"""
import argparse
import json
import sys
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from forward_validation import report_metrics
from market_pair import pair
from odds_market import aggregate
from research_recommender import build

MAX_RECORDS = 2000
MAX_PEAK_MB = 220
MAX_SECONDS = 180
NOW = datetime(2026, 10, 9, 8, tzinfo=timezone.utc)


def fixtures(count):
    """Generate unique league-scoped identities and valid pre-match snapshots."""
    if type(count) is not int or not 1 <= count <= MAX_RECORDS:
        raise ValueError("OUTSIDE_BOUNDED_STRESS_TEST")
    pred = NOW.isoformat()
    market_at = (NOW - timedelta(minutes=12)).isoformat()
    quoted_at = (NOW - timedelta(minutes=14)).isoformat()
    forecast, market = [], []
    for i in range(count):
        league = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")[i % 6]
        home, away = f"StressHome{i}", f"StressAway{i}"
        kickoff = (NOW + timedelta(days=2, minutes=i % 50)).isoformat()
        forecast.append({"league": league, "home": home, "away": away,
                         "prediction_utc": pred, "kickoff_utc": kickoff,
                         "p_home": .61, "p_draw": .24, "p_away": .15,
                         "production_recommendations": "DISABLED"})
        market.append({"league": league, "home": home, "away": away,
                       "source_event_id": f"mock-{i}", "kickoff_utc": kickoff,
                       "market_last_update_utc": quoted_at,
                       "p_home": .52, "p_draw": .26, "p_away": .22,
                       "production_recommendations": "DISABLED"})
    shadow = {"status": "SHADOW_ONLY", "as_of_utc": pred,
              "predictions": forecast, "production_recommendations": "DISABLED"}
    odds = {"status": "RESEARCH_ONLY", "as_of_utc": market_at,
            "events": market, "production_recommendations": "DISABLED"}
    return shadow, odds


def run(count):
    started = time.perf_counter()
    tracemalloc.start()
    measurements = {}
    shadow, market = fixtures(count)

    tic = time.perf_counter()
    paired = pair(shadow, market)
    measurements["pair_seconds"] = round(time.perf_counter() - tic, 3)
    if paired["matched_count"] != count:
        raise AssertionError(f"PAIR_LOSS: {paired['matched_count']} != {count}")
    if any(x.get("available_for_betting") is not False or
           x.get("production_recommendations") != "DISABLED"
           for x in paired["comparisons"]):
        raise AssertionError("UNSAFE_PAIR_BETTING_FLAG")

    tic = time.perf_counter()
    status = {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED"}
    shortlisted = build(shadow, paired, status, now=NOW)
    measurements["rank_seconds"] = round(time.perf_counter() - tic, 3)
    if shortlisted["selected_count"] > 8 or shortlisted["paired_count"] != count:
        raise AssertionError("UNBOUNDED_RECOMMENDATIONS")
    if shortlisted["production_recommendations"] != "DISABLED":
        raise AssertionError("UNSAFE_RECOMMENDER")

    # Malformed vendor odds must not abort good matches.
    tic = time.perf_counter()
    damaged = 0
    for i in range(max(1000, count)):
        event = {"home_team": "A", "away_team": "B",
                 "id": str(i), "commence_time": (NOW + timedelta(days=1)).isoformat(),
                 "bookmakers": None if i % 3 == 0 else [
                     {"key": "a", "markets": {"bad": i}},
                     {"key": "b", "markets": [{"key": "h2h", "outcomes": None}]}]}
        if aggregate(event, now=NOW) is None:
            damaged += 1
    measurements["malformed_odds_seconds"] = round(time.perf_counter() - tic, 3)
    if damaged != max(1000, count):
        raise AssertionError("MALFORMED_MARKET_ACCEPTED")

    # Simultaneous independent read-only analyses must not share mutable state.
    tic = time.perf_counter()
    small_shadow, small_market = fixtures(60)
    def concurrent_job(_):
        v = pair(small_shadow, small_market)
        return v["matched_count"], v["production_recommendations"]
    with ThreadPoolExecutor(max_workers=8) as workers:
        outcomes = list(workers.map(concurrent_job, range(24)))
    measurements["concurrency_seconds"] = round(time.perf_counter() - tic, 3)
    if outcomes != [(60, "DISABLED")] * 24:
        raise AssertionError("CONCURRENT_READ_DRIFT")

    # Mature forward-only evidence must evaluate without unlocking betting.
    tic = time.perf_counter()
    rows = [{"kickoff_utc": (NOW - timedelta(weeks=i//5 + 1)).isoformat(),
             "p": [.3, .25, .45], "m": [.32, .27, .41],
             "y": i % 3} for i in range(350)]
    evidence = report_metrics({"samples": rows, "newly_settled": 0})
    measurements["forward_seconds"] = round(time.perf_counter() - tic, 3)
    if evidence["forward_archive_samples"] != 350 or not evidence.get("reason"):
        raise AssertionError("FORWARD_EVIDENCE_CORRUPTED")
    if evidence["production_recommendations"] != "DISABLED":
        raise AssertionError("FORWARD_UNLOCKED_BETTING")

    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    duration = time.perf_counter() - started
    result = {"schema": "football-king-offline-stress-v1",
              "data": "SYNTHETIC_ONLY", "network_requests": 0,
              "provider_api_credits": 0, "matched_pairs": count,
              "corrupted_payloads_rejected": damaged,
              "concurrent_jobs": len(outcomes),
              "forward_samples": 350,
              "production_recommendations": "DISABLED",
              "peak_memory_mb": round(peak / (1024 * 1024), 2),
              "duration_seconds": round(duration, 3),
              "phases": measurements, "status": "PASS"}
    if result["peak_memory_mb"] > MAX_PEAK_MB or duration > MAX_SECONDS:
        result["status"] = "FAIL"
        raise AssertionError(json.dumps(result, ensure_ascii=False))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=int, default=500)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    result = run(args.records)
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True)
    if args.output:
        Path(args.output).write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    sys.exit(main())
