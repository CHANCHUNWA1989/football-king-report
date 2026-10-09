"""Reject malformed, stale, unsafe or raw sportsbook market archives."""
import argparse
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

EXPECTED_KEYS = frozenset({
    "league", "source_event_id", "home", "away", "kickoff_utc",
    "market_last_update_utc", "contributing_bookmakers",
    "p_home", "p_draw", "p_away", "probabilities_are_no_vig_consensus",
    "prediction_or_value_bet",
})


def time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_CAPTURE_TIME")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE_TIME")
    return d.astimezone(timezone.utc)


def check(doc, *, legacy_capture_grace_seconds=0):
    if not isinstance(doc, dict):
        raise ValueError("NOT_A_MARKET_RECORD")
    if (doc.get("schema") != "football-king-market-consensus-v1"
            or doc.get("provider") != "the-odds-api.com/v4"
            or doc.get("status") not in ("RESEARCH_ONLY", "HOLD")
            or doc.get("production_recommendations") != "DISABLED"
            or doc.get("raw_bookmaker_quotes_redistributed") is not False):
        raise ValueError("INVALID_MARKET_METADATA")
    captured = time(doc["as_of_utc"])
    # Reject a forged future snapshot that could block all future publication.
    if captured > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("FUTURE_MARKET_SNAPSHOT")
    events = doc.get("events")
    if not isinstance(events, list) or len(events) > 3000 or doc.get("event_count") != len(events):
        raise ValueError("INVALID_MARKET_COUNTS")
    for v in events:
        if not isinstance(v, dict) or not set(v).issubset(EXPECTED_KEYS):
            raise ValueError("UNAUTHORIZED_MARKET_FIELDS")
        if (v.get("prediction_or_value_bet") is not False
                or v.get("probabilities_are_no_vig_consensus") is not True
                or type(v.get("contributing_bookmakers")) is not int
                or v["contributing_bookmakers"] < 2):
            raise ValueError("INVALID_BOOKMAKER_RESEARCH")
        probabilities = [v.get("p_home"), v.get("p_draw"), v.get("p_away")]
        if (not all(type(p) in (float, int) and math.isfinite(p) and 0 <= p <= 1
                    for p in probabilities)
                or abs(sum(probabilities) - 1) > .001):
            raise ValueError("INVALID_MARKET_PROBABILITIES")
        # Older snapshots used the START of the batch as the timestamp.
        # Grace is allowed only when READING those earlier snapshots, never
        # for newly captured data.
        quote_time = time(v["market_last_update_utc"])
        age = (captured - quote_time).total_seconds()
        if age < -legacy_capture_grace_seconds:
            raise ValueError("MARKET_DATA_FROM_FUTURE")
        if age > 8 * 3600:
            raise ValueError("STALE_MARKET_QUOTE")
        if time(v["kickoff_utc"]) <= captured:
            raise ValueError("LIVE_OR_FINISHED_MARKET_NOT_ALLOWED")
    return captured


def latest_can_replace(old, incoming):
    fresh = check(incoming)
    if old is None:
        return True
    previous = check(old, legacy_capture_grace_seconds=300)
    if fresh < previous:
        return False
    if fresh == previous and old != incoming:
        raise ValueError("SAME_CAPTURE_CONFLICT")
    return fresh > previous


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--current", required=True)
    p.add_argument("--incoming", required=True)
    args = p.parse_args()
    previous = json.loads(Path(args.current).read_text(encoding="utf-8")) if Path(args.current).exists() else None
    incoming = json.loads(Path(args.incoming).read_text(encoding="utf-8"))
    allowed = latest_can_replace(previous, incoming)
    print(json.dumps({"safe_update": allowed, "reason": "NEWER_SNAPSHOT" if allowed else "ALREADY_CURRENT_OR_NEWER"}))


if __name__ == "__main__":
    main()
