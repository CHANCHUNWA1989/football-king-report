"""Offline two-publisher fixture overlap audit, never a final-score certification.

Input: already-archived licensed/sanitized provider records. ZERO API requests,
ZERO raw bookmaker prices, ZERO bookmaker identities, ZERO model promotion.
Counts of aligned fixture kickoffs are evidence of agreement, not that either
upstream feed is independently sourced or the game outcome is correct.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from source_publish_guard import verify as verify_sources
from team_identity import team_id

SCHEMA = "football-king-six-league-two-publisher-fixtures-v1"
MARKET_SCHEMA = "football-king-market-consensus-v1"
SECONDARY_SCHEMA = "football-king-extra-source-audit-v1"
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
PROVIDERS = frozenset(("thesportsdb", "api_football", "football_data_org"))
MAX_AGE_HOURS = 36
MAX_MARKET_AGE_HOURS = 26
MATCH_SECONDS = 45 * 60
CONFLICT_SECONDS = 7 * 86400


def stamp(value):
    if not isinstance(value, str):
        raise ValueError("NOT_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return dt.astimezone(timezone.utc)


def ident(row):
    league = row.get("league")
    if league not in LEAGUES:
        return None
    h = team_id(league, row.get("home"))
    a = team_id(league, row.get("away"))
    if not h or not a or h == a:
        return None
    return (league, h, a)


def _row_report(league):
    return {
        "league": league, "market_events": 0,
        "time_valid_market_events": 0,
        "one_other_publisher_agreements": 0,
        "two_other_publisher_agreements": 0,
        "other_publisher_conflicts": 0,
        "ambiguous_or_duplicate_source_events": 0,
        "unmatched_or_unverified_market_events": 0,
    }


def compare(market, sources, *, captured_utc):
    captured = stamp(captured_utc)
    out = {
        "schema": SCHEMA, "captured_utc": captured.isoformat(),
        "status": "HOLD", "market_as_of_utc": None,
        "secondary_as_of_utc": None,
        "market_fresh": False, "secondary_fresh": False,
        "secondary_licensed_source_validation": False,
        "by_league": [_row_report(l) for l in LEAGUES],
        "market_sample_count": 0, "time_valid_market_count": 0,
        "at_least_one_other_publisher_agreement": 0,
        "at_least_two_other_publisher_agreements": 0,
        "source_schedule_conflict_observations": 0,
        "ambiguous_or_duplicate_source_event_observations": 0,
        "independently_verified_final_results": 0,
        "other_publisher_not_independent_bookmaker": True,
        "same_upstream_feed_not_ruled_out": True,
        "all_six_leagues_independently_verified": False,
        "original_bookmaker_quotes_stored": False,
        "model_promotion_authorized": False,
        "production_recommendations": "DISABLED",
    }
    if not isinstance(market, dict) or not isinstance(sources, dict):
        return out
    if (market.get("schema") != MARKET_SCHEMA or
            market.get("status") != "RESEARCH_ONLY" or
            market.get("production_recommendations") != "DISABLED" or
            not isinstance(market.get("events"), list) or
            len(market["events"]) > 3000):
        return out
    try:
        market_at = stamp(market["as_of_utc"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return out
    out["market_as_of_utc"] = market_at.isoformat()
    market_age = (captured-market_at).total_seconds()
    if not -300 <= market_age <= MAX_MARKET_AGE_HOURS*3600:
        return out
    out["market_fresh"] = True
    out["market_sample_count"] = len(market["events"])

    try:
        if sources.get("schema") != SECONDARY_SCHEMA:
            raise ValueError("UNEXPECTED_SECONDARY_SOURCE")
        source_at = verify_sources(sources)
        age = (captured-source_at).total_seconds()
        if not -300 <= age <= MAX_AGE_HOURS*3600:
            out["secondary_as_of_utc"] = source_at.isoformat()
            return out
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return out
    out["secondary_as_of_utc"] = source_at.isoformat()
    out["secondary_fresh"] = True
    out["secondary_licensed_source_validation"] = True

    index = {}
    # A provider may repeat or revise a fixture. Conflicting duplicate
    # observations must not count as corroborating independent evidence.
    for row in sources.get("sampled_fixtures", [])[:1500]:
        if (not isinstance(row, dict) or row.get("provider") not in PROVIDERS
                or row.get("status") not in ("SCHEDULED", "UNKNOWN")):
            continue
        key = ident(row)
        if key is None:
            continue
        try:
            ko = stamp(row["kickoff_utc"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if ko <= source_at:
            continue
        # Unique natural fixture identifier, not the provider event id alone.
        index.setdefault(key, {}).setdefault(row["provider"], []).append(ko)

    for league, row_out in zip(LEAGUES, out["by_league"]):
        market_seen = set()
        for row in market["events"]:
            if not isinstance(row, dict) or row.get("league") != league:
                continue
            row_out["market_events"] += 1
            key = ident(row)
            if key is None:
                continue
            try:
                ko, updated = stamp(row["kickoff_utc"]), stamp(row["market_last_update_utc"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if not (updated <= market_at < ko - timedelta(minutes=10)):
                continue
            source_id = row.get("source_event_id")
            event_key = (key, ko, source_id)
            if not source_id or event_key in market_seen:
                continue
            market_seen.add(event_key)
            row_out["time_valid_market_events"] += 1
            agreements = 0
            conflict = False
            for provider, timestamps in index.get(key, {}).items():
                # Repeated rows from same provider are not independent.
                if len(timestamps) != 1:
                    row_out["ambiguous_or_duplicate_source_events"] += 1
                    continue
                delta = abs((timestamps[0]-ko).total_seconds())
                if delta <= MATCH_SECONDS:
                    agreements += 1
                elif delta <= CONFLICT_SECONDS:
                    conflict = True
                    row_out["other_publisher_conflicts"] += 1
            # Any contradictory timestamp must HOLD the per-fixture evidence.
            if conflict:
                continue
            if agreements >= 1:
                row_out["one_other_publisher_agreements"] += 1
            if agreements >= 2:
                row_out["two_other_publisher_agreements"] += 1
        row_out["unmatched_or_unverified_market_events"] = (
            row_out["time_valid_market_events"] -
            row_out["one_other_publisher_agreements"])
        out["time_valid_market_count"] += row_out["time_valid_market_events"]
        out["at_least_one_other_publisher_agreement"] += row_out["one_other_publisher_agreements"]
        out["at_least_two_other_publisher_agreements"] += row_out["two_other_publisher_agreements"]
        out["source_schedule_conflict_observations"] += row_out["other_publisher_conflicts"]
        out["ambiguous_or_duplicate_source_event_observations"] += row_out["ambiguous_or_duplicate_source_events"]
    out["status"] = "RESEARCH_ONLY"
    return out


def validate(out):
    if (not isinstance(out, dict) or out.get("schema") != SCHEMA
            or out.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or out.get("production_recommendations") != "DISABLED"
            or out.get("all_six_leagues_independently_verified") is not False
            or out.get("model_promotion_authorized") is not False
            or out.get("original_bookmaker_quotes_stored") is not False
            or out.get("same_upstream_feed_not_ruled_out") is not True
            or out.get("independently_verified_final_results") != 0
            or [x.get("league") for x in out.get("by_league", [])] != list(LEAGUES)):
        raise ValueError("UNSAFE_CROSS_SOURCE_STATUS")
    for field in ("market_sample_count", "time_valid_market_count",
                  "at_least_one_other_publisher_agreement",
                  "at_least_two_other_publisher_agreements"):
        if type(out.get(field)) is not int or not 0 <= out[field] <= 3000:
            raise ValueError("INVALID_SOURCE_EVIDENCE_COUNT")
    if not (out["at_least_two_other_publisher_agreements"] <=
            out["at_least_one_other_publisher_agreement"] <=
            out["time_valid_market_count"] <= out["market_sample_count"]):
        raise ValueError("IMPOSSIBLE_CORROBORATION")
    for row in out["by_league"]:
        for field in ("market_events", "time_valid_market_events",
                      "one_other_publisher_agreements", "two_other_publisher_agreements",
                      "unmatched_or_unverified_market_events"):
            if type(row.get(field)) is not int or not 0 <= row[field] <= 3000:
                raise ValueError("INVALID_PER_LEAGUE_COUNT")
        if not (row["two_other_publisher_agreements"] <=
                row["one_other_publisher_agreements"] <=
                row["time_valid_market_events"] <= row["market_events"]):
            raise ValueError("IMPOSSIBLE_LEAGUE_PROVENANCE")
    return True


def load(path):
    try:
        target = Path(path)
        if not target.is_file() or target.stat().st_size > 3_000_000:
            return None
        return json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--market", default="market/latest.json")
    p.add_argument("--sources", default="sources/latest.json")
    p.add_argument("--six", required=True)
    p.add_argument("--output", default="fixture-overlap.json")
    a = p.parse_args()
    six = load(a.six)
    if not isinstance(six, dict) or six.get("schema") != "football-king-six-free-league-quality-v1":
        raise ValueError("MISSING_SIX_LEAGUE_CAPTURE")
    item = compare(load(a.market), load(a.sources), captured_utc=six["captured_utc"])
    validate(item)
    Path(a.output).write_text(json.dumps(item, ensure_ascii=False, indent=2)+"\n",
                              encoding="utf-8")
    print(json.dumps({
        "status": item["status"],
        "one_other_publisher": item["at_least_one_other_publisher_agreement"],
        "two_other_publishers": item["at_least_two_other_publisher_agreements"],
        "time_valid_market_count": item["time_valid_market_count"],
        "source_conflicts": item["source_schedule_conflict_observations"],
        "production_recommendations": "DISABLED",
    }))


if __name__ == "__main__":
    main()
