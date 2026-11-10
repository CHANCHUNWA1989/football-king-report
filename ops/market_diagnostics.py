"""Read-only diagnostics for Football King market snapshot quality.

No provider calls, no credential access, no recommendation promotion.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _utc(value):
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp.astimezone(timezone.utc) if stamp.tzinfo else None


def diagnose(snapshot, *, now_utc, max_age_minutes=15):
    now = _utc(now_utc)
    if now is None:
        raise ValueError("INVALID_NOW_UTC")
    if not isinstance(snapshot, dict):
        return {"status": "HOLD", "blockers": ["INVALID_MARKET_SNAPSHOT"],
                "production_recommendations": "DISABLED"}
    blockers = []
    stamp = _utc(snapshot.get("as_of_utc"))
    if stamp is None or not 0 <= (now - stamp).total_seconds() <= max_age_minutes * 60:
        blockers.append("MARKET_SNAPSHOT_STALE_OR_UNDATED")
    quota = snapshot.get("quota")
    policy = snapshot.get("quota_policy")
    if isinstance(quota, dict) and isinstance(policy, dict):
        used, remaining = quota.get("used"), quota.get("remaining")
        max_used, floor = policy.get("max_monthly_used"), policy.get("remaining_floor")
        if all(type(v) is int for v in (used, remaining, max_used, floor)):
            if used >= max_used or remaining <= floor:
                blockers.append("API_QUOTA_GUARD")
    markets = snapshot.get("requested_markets")
    if not isinstance(markets, list) or "totals" not in markets:
        blockers.append("TOTALS_MARKET_NOT_REQUESTED")
    if not isinstance(markets, list) or "spreads" not in markets:
        blockers.append("SPREADS_MARKET_NOT_REQUESTED")
    if snapshot.get("handicap_and_totals_verified") is not True:
        blockers.append("HANDICAP_TOTALS_NOT_VERIFIED")
    if snapshot.get("status") not in ("RESEARCH_ONLY", "READY_RESEARCH"):
        blockers.append("MARKET_STATUS_NOT_READY")
    return {
        "schema": "football-king-market-diagnostics-v1",
        "status": "HOLD" if blockers else "RESEARCH_ONLY",
        "blockers": blockers,
        "market_snapshot_utc": snapshot.get("as_of_utc"),
        "requested_markets": markets if isinstance(markets, list) else [],
        "provider_calls_made": 0,
        "production_recommendations": "DISABLED",
        "betting_permission": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="market/latest.json")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    try:
        snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        snapshot = None
    report = diagnose(snapshot, now_utc=datetime.now(timezone.utc).isoformat())
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if report["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
