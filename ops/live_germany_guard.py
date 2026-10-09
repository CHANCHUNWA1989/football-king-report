"""Validate live German source snapshots before public publishing."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from live_germany import SHORTCUTS, MAX_OUTPUT_MATCHES, API_LICENSE


def stamp(s):
    t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("LIVE_TIMESTAMP_UNZONED")
    return t.astimezone(timezone.utc)


def verify(doc, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(doc, dict) or doc.get("schema") != "football-king-openligadb-hourly-v1":
        raise ValueError("INVALID_OPENLIGA_LIVE_SCHEMA")
    if (doc.get("source") != "OpenLigaDB"
            or doc.get("source_type") != "COMMUNITY_CONTRIBUTED_NOT_OFFICIAL_LIVE"
            or doc.get("licence") != "ODbL" or doc.get("licence_url") != API_LICENSE
            or doc.get("live_second_by_second_guaranteed") is not False
            or doc.get("provider_last_modified_known") is not False
            or doc.get("six_league_results_independently_verified") is not False
            or doc.get("replaces_bookmaker_market") is not False
            or doc.get("used_to_refit_model") is not False
            or doc.get("production_recommendations") != "DISABLED"
            or doc.get("status") not in ("HOLD", "RESEARCH_ONLY")
            or doc.get("calls_attempted") != 3
            or doc.get("max_calls") != 3):
        raise ValueError("UNSAFE_LIVE_RESEARCH_STATE")
    collected = stamp(doc["collected_utc"])
    if (collected - now).total_seconds() > 300 or (now - collected).total_seconds() > 15 * 60:
        raise ValueError("STALE_OR_FUTURE_LIVE_SNAPSHOT")
    coverage = doc.get("league_coverage")
    games = doc.get("matches")
    if (not isinstance(coverage, list) or len(coverage) != 3
            or not isinstance(games, list) or len(games) > MAX_OUTPUT_MATCHES
            or {x.get("league") for x in coverage if isinstance(x, dict)} != set(SHORTCUTS)):
        raise ValueError("INVALID_GERMAN_LIVE_COVERAGE")
    statuses = {"AVAILABLE", "EMPTY_CURRENT_MATCHDAY", "NETWORK_ERROR",
                "RATE_LIMITED", "HTTP_ERROR", "BAD_SCHEMA"}
    for x in coverage:
        if (x.get("status") not in statuses
                or x.get("source") != "openligadb"
                or x.get("production_recommendations") != "DISABLED"
                or type(x.get("matches_in_display_window")) is not int
                or x["matches_in_display_window"] < 0):
            raise ValueError("INVALID_GERMAN_LIVE_PROVIDER")
    seen = set()
    for row in games:
        if not isinstance(row, dict) or set(row) != {
                "league", "home", "away", "provider_match_id", "kickoff_utc", "status", "score_ft"}:
            raise ValueError("RAW_OR_UNAUTHORIZED_LIVE_FIELDS")
        if (row["league"] not in SHORTCUTS or not row["home"] or not row["away"]
                or type(row["provider_match_id"]) is not int
                or row["provider_match_id"] <= 0
                or row["status"] not in ("SCHEDULED", "STARTED_STATUS_UNCONFIRMED",
                                      "FINISHED_SCORE_PENDING", "FINISHED_CONFIRMED_BY_SOURCE")):
            raise ValueError("UNSAFE_GERMAN_LIVE_ROW")
        ko = stamp(row["kickoff_utc"])
        if abs((ko - collected).total_seconds()) > 16 * 86400:
            raise ValueError("GERMAN_MATCH_OUTSIDE_SAFE_WINDOW")
        if row["score_ft"] is not None and (
                row["status"] != "FINISHED_CONFIRMED_BY_SOURCE"
                or not isinstance(row["score_ft"], list)
                or len(row["score_ft"]) != 2
                or any(type(n) is not int or not 0 <= n <= 30 for n in row["score_ft"])):
            raise ValueError("FAKE_FINISHED_SCORE")
        if row["score_ft"] is None and row["status"] == "FINISHED_CONFIRMED_BY_SOURCE":
            raise ValueError("MISSING_FINISHED_SCORE")
        key = (row["league"], row["provider_match_id"])
        if key in seen:
            raise ValueError("DUPLICATE_LIVE_MATCH_ID")
        seen.add(key)
    return collected


def publication(new, old=None, now=None):
    new_stamp = verify(new, now)
    if old is None:
        return True
    oldstamp = stamp(old.get("collected_utc"))
    if new_stamp == oldstamp and new != old:
        raise ValueError("LIVE_SAME_TIME_CONFLICT")
    return new_stamp > oldstamp


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--input", required=True)
    cli.add_argument("--previous")
    cli.add_argument("--decision")
    args = cli.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    old = json.loads(Path(args.previous).read_text(encoding="utf-8")) if args.previous else None
    should = publication(data, old)
    if args.decision:
        Path(args.decision).write_text(json.dumps({"replace": should})+"\n", encoding="utf-8")
    print(json.dumps({"valid": True, "replace": should, "matches": len(data["matches"]),
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
