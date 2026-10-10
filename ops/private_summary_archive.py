"""Archive only de-identified, zero-odds private market coverage metadata.

The provider key and raw bookmaker prices must NEVER enter a public commit.
Missing, stale, or malformed observations cannot overwrite newer evidence.
"""
import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCHEMA = "football-king-public-artifact-summary-v1"
LEAGUES = frozenset(("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1"))
MARKETS = frozenset(("h2h", "spreads", "totals"))
STATUSES = frozenset(("CONNECTED", "QUOTA_GUARD", "MISSING_API_KEY",
                      "PROVIDER_ERROR", "NO_ACTIVE_LEAGUES", "UNKNOWN"))
COUNTS = ("RESEARCH_ONLY", "STALE", "INCOMPLETE", "INVALID",
          "VERIFIED_VALUE", "NO_VALUE")

def utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_OBSERVATION_TIMESTAMP")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_OBSERVATION_TIMESTAMP")
    return dt.astimezone(timezone.utc)

def check(doc, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA:
        raise ValueError("INVALID_SANITIZED_SCHEMA")
    if (doc.get("production_recommendations") != "DISABLED"
            or doc.get("raw_prices_or_bookmakers_included") is not False
            or doc.get("quotes_are_executable") is not False
            or doc.get("verified_bets") != 0):
        raise ValueError("UNSAFE_OR_VERIFIED_BETS_CLAIM")
    if doc.get("input_status") not in STATUSES:
        raise ValueError("UNKNOWN_COLLECTOR_STATUS")
    date = utc(doc.get("captured_utc"))
    if (now - date > timedelta(days=30)
            or date - now > timedelta(minutes=5)):
        raise ValueError("STALE_OR_FUTURE_PUBLIC_COVERAGE")
    counts = doc.get("counts")
    if not isinstance(counts, dict) or set(counts) != set(COUNTS):
        raise ValueError("INVALID_MARKET_COUNTS")
    if any(type(counts[k]) is not int or not 0 <= counts[k] <= 100_000 for k in COUNTS):
        raise ValueError("INVALID_MARKET_COUNT")
    if counts["VERIFIED_VALUE"] != 0:
        raise ValueError("UNTRUSTED_VERIFIED_VALUE")
    cover = doc.get("coverage")
    if not isinstance(cover, list) or len(cover) > 6:
        raise ValueError("INVALID_COVERAGE")
    seen = set()
    for item in cover:
        if (not isinstance(item, dict) or set(item) != {"league", "quotes", "status"}
                or item.get("league") not in LEAGUES
                or item.get("status") != "COUNTS_ONLY"
                or type(item.get("quotes")) is not int
                or not 0 <= item["quotes"] <= 100_000
                or item["league"] in seen):
            raise ValueError("INVALID_COVERAGE_ITEM")
        seen.add(item["league"])
    markets = doc.get("requested_markets")
    if (not isinstance(markets, list) or len(markets) > 3
            or len(set(markets)) != len(markets)
            or any(m not in MARKETS for m in markets)):
        raise ValueError("INVALID_REQUESTED_MARKETS")
    allowed_keys = frozenset(("schema", "captured_utc", "input_status", "counts",
                              "coverage", "requested_markets", "evidence_progress",
                              "production_recommendations",
                              "raw_prices_or_bookmakers_included",
                              "quotes_are_executable", "verified_bets"))
    if set(doc) != allowed_keys:
        # Prevent inadvertent leaking of new metadata fields or provider names.
        raise ValueError("UNAPPROVED_PUBLIC_FIELDS")
    progress = doc.get("evidence_progress")
    if not isinstance(progress, dict) or len(progress) > 20:
        raise ValueError("INVALID_EVIDENCE_PROGRESS")
    if any(not isinstance(k, str) or type(v) is not int or not 0 <= v <= 20000
           for k, v in progress.items()):
        raise ValueError("INVALID_EVIDENCE_PROGRESS_ITEM")
    # Values are aggregates only: no fixture, team, bookmaker or prices.
    return date

def prepare(current, incoming, now=None):
    now = now or datetime.now(timezone.utc)
    newtime = check(incoming, now)
    if current is not None:
        try:
            oldtime = check(current, now)
        except ValueError:
            oldtime = None
        if oldtime is not None and oldtime >= newtime:
            return current, False
    # Rebuild just the already whitelist-validated data.
    return {k: incoming[k] for k in (
        "schema", "captured_utc", "input_status", "counts", "coverage",
        "requested_markets", "evidence_progress", "production_recommendations",
        "raw_prices_or_bookmakers_included", "quotes_are_executable", "verified_bets")}, True

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--current", required=True)
    p.add_argument("--incoming", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    def read(path):
        target = Path(path)
        if not target.is_file():
            return None
        if target.stat().st_size > 60_000:
            raise ValueError("PUBLIC_AGGREGATE_TOO_LARGE")
        return json.loads(target.read_text(encoding="utf-8"))
    merged, updated = prepare(read(args.current), read(args.incoming))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("PUBLIC_COVERAGE_UPDATED:", updated,
          "SOURCE_STATUS:", merged["input_status"],
          "RESEARCH_OBSERVATIONS:", merged["counts"]["RESEARCH_ONLY"],
          "FORMAL_RECOMMENDATIONS:", 0)

if __name__ == "__main__":
    main()
