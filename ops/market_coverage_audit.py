"""Read-only market coverage audit: query intent is not observed market data.

Public h2h no-vig consensus is not a bookmaker price. Private redacted
aggregate counts cannot establish which Asian line or bookmaker was observed.
No odds requests, source rights, model calibration or wagering activation.
"""
import argparse
import json
import math
from pathlib import Path

MARKETS = ("h2h", "spreads", "totals")


def _public_h2h_consensus_observed(snapshot):
    """Identify one structural public h2h consensus, NOT executable odds."""
    if (snapshot.get("market") != "h2h"
            or snapshot.get("status") != "RESEARCH_ONLY"
            or snapshot.get("production_recommendations") != "DISABLED"):
        return False
    count = snapshot.get("event_count")
    events = snapshot.get("events")
    if type(count) is not int or count <= 0 or not isinstance(events, list) or len(events) != count:
        return False
    # Check the full snapshot, not just the first event, so a partially
    # corrupted export cannot be presented as positive data coverage.
    seen_ids = set()
    for row in events:
        if not isinstance(row, dict) or not isinstance(row.get("source_event_id"), str) or not row["source_event_id"]:
            return False
        if row["source_event_id"] in seen_ids:
            return False
        seen_ids.add(row["source_event_id"])
        probabilities = [row.get(key) for key in ("p_home", "p_draw", "p_away")]
        if (any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1
                for p in probabilities)
                or abs(sum(probabilities) - 1) > 1e-5):
            return False
    return True


def audit(market_snapshot, private_summary):
    if not isinstance(market_snapshot, dict) or not isinstance(private_summary, dict):
        raise ValueError("INVALID_INPUT")
    requested = private_summary.get("requested_markets", [])
    if (not isinstance(requested, list)
            or any(type(m) is not str or m not in MARKETS for m in requested)
            or len(requested) != len(set(requested))):
        raise ValueError("INVALID_MARKET_LIST")
    # A requested market merely records collection intent. Neither that field,
    # nor aggregated quote counts or caller-supplied verification flags, proves
    # actual spreads/totals observations or licensed, executable bookmaker odds.
    observed_consensus = ["h2h"] if _public_h2h_consensus_observed(market_snapshot) else []
    not_observed = [m for m in MARKETS if m not in observed_consensus]
    return {
        "schema": "football-king-market-coverage-audit-v1",
        "as_of_utc": market_snapshot.get("as_of_utc"),
        "requested_markets": [m for m in MARKETS if m in requested],
        "observed_consensus_markets": observed_consensus,
        "requested_but_unobserved": [m for m in MARKETS if m in requested and m not in observed_consensus],
        "missing_markets": not_observed,
        # The redacted private summary intentionally contains no raw prices,
        # bookmaker identities, exact market lines, or independent receipts.
        # Thus price-level coverage must remain unverified even when all
        # three markets were requested in the upstream collector.
        "market_coverage_complete": False,
        "handicap_available": False,
        "totals_available": False,
        "raw_prices_verified": False,
        "can_recommend_handicap_or_totals": False,
        "reason": "MARKET_LEVEL_RAW_QUOTES_NOT_INDEPENDENTLY_VERIFIED",
        "production_recommendations": "DISABLED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="market/latest.json")
    parser.add_argument("--summary", default="market/private_summary_latest.json")
    parser.add_argument("--output", default="market/coverage_audit.json")
    args = parser.parse_args()
    report = audit(json.loads(Path(args.market).read_text()),
                   json.loads(Path(args.summary).read_text()))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"missing_markets": report["missing_markets"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
