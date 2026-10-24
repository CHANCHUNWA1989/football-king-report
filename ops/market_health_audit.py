"""Read-only health audit for cached free odds; never makes network/API calls.

Usage: python ops/market_health_audit.py --market market/latest.json --status market/collection_status.json
Exit 0 = research cache healthy, 1 = HOLD, 2 = malformed input.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("naive timestamp")
    return dt.astimezone(timezone.utc)


def audit(market, status, now=None, max_snapshot_age_minutes=180,
          max_quote_age_minutes=30):
    now = now or datetime.now(timezone.utc)
    reasons = []
    captured = timestamp(market["as_of_utc"])
    age = (now - captured).total_seconds() / 60
    if age < -5 or age > max_snapshot_age_minutes:
        reasons.append("SNAPSHOT_STALE_OR_FUTURE")
    events = market.get("events", [])
    if not isinstance(events, list) or market.get("event_count") != len(events):
        raise ValueError("invalid event count")
    stale = 0
    for event in events:
        quote_age = (now - timestamp(event["market_last_update_utc"])).total_seconds() / 60
        if quote_age < 0 or quote_age > max_quote_age_minutes:
            stale += 1
    if stale:
        reasons.append("STALE_EVENT_QUOTES")
    if not events:
        reasons.append("NO_EVENTS")
    elif any(timestamp(event["kickoff_utc"]) <= now for event in events if "kickoff_utc" in event):
        reasons.append("LIVE_OR_FINISHED_EVENT_IN_CACHE")
    if market.get("status") != "RESEARCH_ONLY" or status.get("collection_status") != "RESEARCH_ONLY":
        reasons.append("COLLECTION_NOT_READY")
    if status.get("as_of_utc") != market.get("as_of_utc"):
        reasons.append("STATUS_MARKET_MISMATCH")
    quota = status.get("quota") or {}
    remaining, used = quota.get("remaining"), quota.get("used")
    if type(remaining) is not int or type(used) is not int or remaining < 0 or used < 0:
        reasons.append("UNKNOWN_QUOTA")
    elif remaining <= 140 or used >= 360:
        reasons.append("QUOTA_GUARD")
    missing = market.get("missing_markets", [])
    if not isinstance(missing, list) or any(not isinstance(m, str) for m in missing):
        raise ValueError("invalid missing markets")
    if any(m in ("h2h", "spreads", "totals") for m in missing):
        reasons.append("UNVERIFIED_MARKET_COVERAGE")
    return {
        "status": "RESEARCH_ONLY" if not reasons else "HOLD",
        "reasons": reasons,
        "as_of_utc": market["as_of_utc"],
        "snapshot_age_minutes": round(age, 2),
        "event_count": len(events),
        "stale_event_count": stale,
        "quota_remaining": remaining,
        "quota_used": used,
        "missing_markets": missing,
        "production_recommendations": "DISABLED",
        "executable_odds_verified": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="market/latest.json")
    parser.add_argument("--status", default="market/collection_status.json")
    args = parser.parse_args()
    try:
        result = audit(json.loads(Path(args.market).read_text()),
                       json.loads(Path(args.status).read_text()))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(json.dumps({"status": "HOLD", "reason": "INVALID_CACHE", "error_type": type(exc).__name__,
                          "production_recommendations": "DISABLED"}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "RESEARCH_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
