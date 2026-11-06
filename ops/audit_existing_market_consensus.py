"""Read-only inspection of the existing 1X2 market consensus artifact.

Consensus probabilities are not executable bookmaker odds. No EV calculation.
"""
import argparse
import json
from collections import Counter
from datetime import datetime


def inspect_market(data):
    if not isinstance(data, dict) or data.get("status") != "RESEARCH_ONLY":
        raise ValueError("market artifact must be research-only")
    events = data.get("events")
    if not isinstance(events, list) or len(events) > 10000:
        raise ValueError("invalid events")
    markets = data.get("requested_markets", [])
    if not isinstance(markets, list):
        raise ValueError("invalid requested markets")
    missing = Counter()
    leagues = Counter()
    seen = set()
    valid_consensus = 0
    for event in events:
        if not isinstance(event, dict):
            missing["invalid_event"] += 1
            continue
        identity = event.get("source_event_id")
        if not isinstance(identity, str) or not identity or identity in seen:
            missing["invalid_or_duplicate_event_id"] += 1
            continue
        seen.add(identity)
        try:
            kickoff = datetime.fromisoformat(event["kickoff_utc"].replace("Z", "+00:00"))
            updated = datetime.fromisoformat(event["market_last_update_utc"].replace("Z", "+00:00"))
            if (kickoff.utcoffset() is None or updated.utcoffset() is None
                    or not updated < kickoff):
                raise ValueError("bad chronology")
            p = [event[k] for k in ("p_home", "p_draw", "p_away")]
            if (any(type(x) not in (int, float) or not 0 <= x <= 1 for x in p)
                    or abs(sum(p) - 1) > 0.002
                    or event.get("probabilities_are_no_vig_consensus") is not True):
                raise ValueError("invalid consensus")
        except (KeyError, ValueError, TypeError, OverflowError, AttributeError):
            missing["invalid_consensus_or_time"] += 1
            continue
        valid_consensus += 1
        leagues[str(event.get("league", "unknown"))] += 1
        # This schema has no individual executable bookmaker quote/price.
        missing["executable_bookmaker_odds"] += 1
        missing["asian_handicap_line"] += 1
        missing["totals_line"] += 1
        missing["independently_attested_capture"] += 1
    return {
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "source_as_of_utc": data.get("as_of_utc"),
        "input_events": len(events),
        "valid_1x2_consensus_events": valid_consensus,
        "league_counts": dict(sorted(leagues.items())),
        "missing_fields_per_valid_event": dict(sorted(missing.items())),
        "requested_markets": markets,
        "missing_markets": data.get("missing_markets", []),
        "asian_ev_calculable": False,
        "executable_1x2_ev_calculable": False,
        "warning": "Market consensus is a de-vigged research baseline, not executable odds.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact")
    args = parser.parse_args()
    with open(args.artifact, encoding="utf-8") as stream:
        result = inspect_market(json.load(stream))
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
