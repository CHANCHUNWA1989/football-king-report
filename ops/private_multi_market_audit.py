"""Offline, zero-credit multi-market quote quality audit (research only).

Accepts a local The Odds API event response. Never persists bookmaker names,
decimal prices or event-level private quote records.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from market_quote_gate import extract

MARKETS = ("h2h", "spreads", "totals")


def audit(payload, captured_utc, *, max_age_seconds=120):
    if not isinstance(payload, list) or len(payload) > 200:
        raise ValueError("INVALID_EVENTS")
    totals = Counter()
    rejected = Counter()
    matched = 0
    # Repeated event IDs are ambiguous; quarantine every copy rather than
    # allowing duplicates to inflate market coverage or sample counts.
    id_counts = Counter(
        event["id"] for event in payload
        if isinstance(event, dict) and isinstance(event.get("id"), str)
        and event["id"].strip()
    )
    for event in payload:
        if not isinstance(event, dict):
            rejected["INVALID_EVENT"] += 1
            continue
        if isinstance(event.get("id"), str) and id_counts[event["id"]] > 1:
            rejected["DUPLICATE_EVENT_ID"] += 1
            continue
        try:
            report = extract(
                [event], captured_utc=captured_utc,
                league=event["sport_key"], home=event["home_team"],
                away=event["away_team"], max_age_seconds=max_age_seconds)
        except (KeyError, ValueError, TypeError):
            rejected["INVALID_EVENT_IDENTITY_OR_TIME"] += 1
            continue
        matched += report["matched_events"]
        for quote in report["quotes"]:
            if quote["quote_pre_match_at_capture"]:
                totals[quote["market"]] += 1
            else:
                rejected["IN_PLAY_OR_TOO_LATE"] += 1
        rejected.update(report["reject_reasons"])
    return {
        "schema": "football-king-private-multi-market-audit-v1",
        "captured_utc": captured_utc,
        "events_matched": matched,
        "fresh_prematch_observations_by_market": {
            market: totals[market] for market in MARKETS
        },
        "missing_markets": [market for market in MARKETS if not totals[market]],
        "rejections": dict(sorted(rejected.items())),
        "bookmaker_prices_persisted": False,
        "independent_model_ev_verified": False,
        "status": "RESEARCH_ONLY" if sum(totals.values()) else "HOLD",
        "production_recommendations": "DISABLED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--captured-utc", required=True)
    parser.add_argument("--output", default="market/private_multi_market_audit.json")
    args = parser.parse_args()
    report = audit(json.loads(Path(args.input).read_text(encoding="utf-8")),
                   args.captured_utc)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"status": report["status"],
                      "missing_markets": report["missing_markets"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
