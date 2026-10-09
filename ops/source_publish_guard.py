"""Strong schema and timeliness gate for publicly archived free-source audits.

Never publish credentials, raw commercial prices, provider response objects
or implied six-league independent result verification.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

PROVIDERS = ("thesportsdb", "api_football", "football_data_org", "sportmonks")
STATUS = ("NOT_CONFIGURED", "HOLD", "PARTIAL", "PARTIAL_COVERAGE", "NO_FIXTURES_RETURNED")
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MAX_PUBLIC_FIXTURES = 150
FORBIDDEN = ("api_key", "api_token", "secret", "access_token", "authorization",
             "x-auth-token", "x-apisports-key", "bet365",
             "raw_odds", "stake", "odd_price")


def time(v):
    if not isinstance(v, str):
        raise ValueError("MISSING_TIMESTAMP")
    d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)


def verify(value):
    if not isinstance(value, dict):
        raise ValueError("BAD_SOURCE_AUDIT")
    if (value.get("schema") != "football-king-extra-source-audit-v1"
            or value.get("production_recommendations") != "DISABLED"
            or value.get("six_league_independent_results_verified") is not False
            or value.get("odds_fallback_confirmed") is not False
            or value.get("coverage_is_complete") is not False
            or value.get("original_api_payload_redistributed") is not False):
        raise ValueError("MISLEADING_SOURCE_PROVENANCE")
    from_time, to_time = time(value["started_utc"]), time(value["collected_utc"])
    if to_time < from_time or (to_time-from_time).total_seconds() > 20*60:
        raise ValueError("SOURCE_TIMESTAMPS_INCONSISTENT")
    if (to_time - datetime.now(timezone.utc)).total_seconds() > 300:
        raise ValueError("COLLECTED_IN_FUTURE")
    rows = value.get("sampled_fixtures")
    providers = value.get("providers")
    if (not isinstance(rows, list) or len(rows) > MAX_PUBLIC_FIXTURES
            or not isinstance(providers, list) or len(providers) != 4
            or tuple(p.get("provider") for p in providers if isinstance(p, dict)) != PROVIDERS):
        raise ValueError("INVALID_PROVIDER_COLLECTION")
    for p in providers:
        if (p.get("status") not in STATUS or type(p.get("configured")) is not bool
                or p.get("production_recommendations") != "DISABLED"
                or p.get("can_replace_1x2_market") is not False
                or p.get("original_bookmaker_odds_redistributed") is not False
                or p.get("league_result_verification_complete") is not False
                or type(p.get("calls_attempted")) is not int or p["calls_attempted"] < 0
                or p["calls_attempted"] > {"thesportsdb":48, "api_football":12,
                                          "football_data_org":6, "sportmonks":2}[p["provider"]]
                or not isinstance(p.get("counts_by_league"), dict)
                or set(p["counts_by_league"]) != set(LEAGUES)):
            raise ValueError("UNSAFE_SOURCE_PROVIDER_METADATA")
    # A free provider's claimed totals must reconcile to the actual public
    # fixture sample. Prevent inflated coverage claims from entering the site.
    observed_counts = {p: {league: 0 for league in LEAGUES} for p in PROVIDERS}
    for row in rows:
        if not isinstance(row, dict) or row.get("provider") not in observed_counts or row.get("league") not in LEAGUES:
            raise ValueError("UNSAFE_SOURCE_FIXTURE")
        observed_counts[row["provider"]][row["league"]] += 1
    for p in providers:
        counts = p["counts_by_league"]
        if (any(type(counts[league]) is not int or counts[league] < 0
                for league in LEAGUES)
                or p.get("sampled_fixture_count") != sum(counts.values())
                or counts != observed_counts[p["provider"]]):
            raise ValueError("SOURCE_COVERAGE_TOTALS_MISMATCH")
    allowed = {"league", "home", "away", "kickoff_utc", "provider_event_id",
               "status", "score_ft", "provider"}
    for row in rows:
        if not isinstance(row, dict) or not set(row).issubset(allowed):
            raise ValueError("RAW_SOURCE_DATA_NOT_ALLOWED")
        if (row.get("league") not in LEAGUES or row.get("provider") not in PROVIDERS
                or row.get("status") not in ("SCHEDULED", "FINISHED", "UNKNOWN")
                or not all(isinstance(row.get(k), str) and 0 < len(row[k]) <= limit
                           for k, limit in (("home", 100), ("away", 100),
                                            ("provider_event_id", 80)))
                or row["home"] == row["away"]):
            raise ValueError("UNSAFE_SOURCE_FIXTURE")
        time(row["kickoff_utc"])
        if row.get("score_ft") is not None:
            if (row.get("status") != "FINISHED"
                    or not isinstance(row["score_ft"], list)
                    or len(row["score_ft"]) != 2
                    or not all(type(s) is int and 0 <= s <= 30 for s in row["score_ft"])):
                raise ValueError("UNSAFE_SOURCE_SCORE")
    # Avoid accidentally persisting token values in novel metadata.
    all_keys = set()
    def scan(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                all_keys.add(str(k).lower())
                scan(v)
        elif isinstance(obj, list):
            for v in obj:
                scan(v)
    scan(value)
    if any(any(needle in key for needle in FORBIDDEN) for key in all_keys):
        raise ValueError("UNEXPECTED_PRIVATE_OR_BETTING_FIELDS")
    return to_time


def should_replace(new, old):
    n = verify(new)
    if old is None:
        return True
    o = verify(old)
    if n == o and new != old:
        raise ValueError("SAME_TIMESTAMP_DIFFERENT_SOURCE_REPORT")
    return n > o


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--previous", default="")
    p.add_argument("--decision", default="")
    args = p.parse_args()
    incoming = json.loads(Path(args.input).read_text(encoding="utf-8"))
    prior = json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous and Path(args.previous).is_file() else None
    replace = should_replace(incoming, prior)
    if args.decision:
        Path(args.decision).write_text(json.dumps({"replace": replace})+"\n", encoding="utf-8")
    print(json.dumps({"public_audit_valid": True,"replace": replace,
                      "sanitized_sources": len(incoming["providers"]),
                      "observed_events": len(incoming["sampled_fixtures"])}))


if __name__ == "__main__":
    main()
