"""Research-only public market coverage audit: requests are not observations.

Public de-vigged h2h consensus and a count-only private summary cannot prove
that any executable Asian spread or totals line was obtained. This zero-credit
diagnostic does not read or persist bookmaker prices and cannot promote bets.
"""
import argparse
import json
from math import isfinite
from datetime import datetime, timezone
from pathlib import Path

MARKETS = ("h2h", "spreads", "totals")
SCHEMA = "football-king-market-coverage-audit-v1"


def _markets(value):
    if (not isinstance(value, list) or any(
            type(item) is not str or item not in MARKETS for item in value)
            or len(value) != len(set(value))):
        raise ValueError("INVALID_MARKET_LIST")
    return [market for market in MARKETS if market in value]


def _timestamp(value):
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.utcoffset() is None:
            return None
        return instant.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError):
        return None


def _valid_public_h2h_events(rows, count, as_of_utc):
    """Verify internal shape/chronology only, never source authenticity.

    Every row must be the published h2h no-vig vector, not a placeholder or
    quoted bookmaker price. One malformed/duplicate native ID invalidates the
    aggregate report instead of inflating public observations.
    """
    if type(count) is not int or not 0 <= count <= 200:
        return False
    if not isinstance(rows, list) or len(rows) != count or as_of_utc is None:
        return False
    as_of = datetime.fromisoformat(as_of_utc)
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            return False
        native_id = row.get("source_event_id")
        league, home, away = (row.get("league"), row.get("home"), row.get("away"))
        if (not isinstance(native_id, str) or not 1 <= len(native_id.strip()) <= 128
                or native_id in seen
                or not isinstance(league, str) or not 1 <= len(league.strip()) <= 128
                or not isinstance(home, str) or not 1 <= len(home.strip()) <= 128
                or not isinstance(away, str) or not 1 <= len(away.strip()) <= 128
                or home.casefold() == away.casefold()
                or row.get("probabilities_are_no_vig_consensus") is not True
                or row.get("prediction_or_value_bet") is not False
                or type(row.get("contributing_bookmakers")) is not int
                or not 1 <= row["contributing_bookmakers"] <= 60):
            return False
        seen.add(native_id)
        probs = [row.get("p_home"), row.get("p_draw"), row.get("p_away")]
        if (any(type(p) not in (int, float) or not isfinite(p)
                or not 0 < p < 1 for p in probs)
                or abs(sum(probs) - 1) > 0.00001):
            return False
        last_update = _timestamp(row.get("market_last_update_utc"))
        kickoff = _timestamp(row.get("kickoff_utc"))
        if last_update is None or kickoff is None:
            return False
        updated = datetime.fromisoformat(last_update)
        starts = datetime.fromisoformat(kickoff)
        # No in-play, future quote, or stale >8h archived observation.
        if not (updated <= as_of < starts
                and (as_of - updated).total_seconds() <= 8 * 3600):
            return False
    return True


def audit(market_snapshot, private_summary):
    """Count only scope present in BOTH safe public artifacts, not API requests.

    Current market-consensus-v1 publishes h2h only. No possible combination
    of public request flags can certify private bookmaker AH / OU lines.
    """
    if not isinstance(market_snapshot, dict) or not isinstance(private_summary, dict):
        raise ValueError("INVALID_INPUT")
    # Retain requested coverage as a separate diagnostic; it NEVER signals
    # actual quoted prices, bookmaker lines or verified model EV.
    requested = _markets(private_summary.get("requested_markets", []))
    try:
        snapshot_requested = _markets(market_snapshot.get("requested_markets", []))
        missing = _markets(market_snapshot.get("missing_markets", []))
    except ValueError:
        snapshot_requested, missing = [], []
    timestamp = _timestamp(market_snapshot.get("as_of_utc"))
    events = market_snapshot.get("events")
    count = market_snapshot.get("event_count")
    safe_snapshot = (
        market_snapshot.get("schema") == "football-king-market-consensus-v1"
        and market_snapshot.get("status") == "RESEARCH_ONLY"
        and market_snapshot.get("production_recommendations") == "DISABLED"
        and market_snapshot.get("market") == "h2h"
        and snapshot_requested == ["h2h"]
        and missing == ["spreads", "totals"]
        and market_snapshot.get("handicap_and_totals_verified") is False
        and market_snapshot.get("raw_bookmaker_quotes_redistributed") is False
        and market_snapshot.get("raw_bookmaker_names_redistributed") is False
        and market_snapshot.get("model_value_advantage_verified") is False
        and timestamp is not None
        and _valid_public_h2h_events(events, count, timestamp)
    )
    safe_summary = (
        private_summary.get("schema") == "football-king-public-artifact-summary-v1"
        and private_summary.get("production_recommendations") == "DISABLED"
        and private_summary.get("raw_prices_or_bookmakers_included") is False
        and private_summary.get("quotes_are_executable") is False
        and type(private_summary.get("verified_bets")) is int
        and private_summary["verified_bets"] == 0
        and _timestamp(private_summary.get("captured_utc")) is not None
    )
    # This is a public h2h research observation, NOT a verified bookmaker
    # offer. No recorded request for spreads/totals becomes observed coverage.
    observed_h2h = bool(safe_snapshot and safe_summary and count and "h2h" in requested)
    observed = ["h2h"] if observed_h2h else []
    if not safe_snapshot:
        reason = "INVALID_OR_UNVERIFIED_PUBLIC_SNAPSHOT"
    elif not safe_summary:
        reason = "INVALID_OR_UNVERIFIED_PUBLIC_SUMMARY"
    elif not observed_h2h:
        reason = "NO_MATCHED_H2H_CONSENSUS_OBSERVATION"
    else:
        reason = "SPREADS_AND_TOTALS_NOT_OBSERVED"
    return {
        "schema": SCHEMA,
        "as_of_utc": timestamp if safe_snapshot else None,
        "status": "RESEARCH_ONLY" if observed_h2h else "HOLD",
        "requested_markets": requested,
        "snapshot_requested_markets": snapshot_requested,
        "public_consensus_observed_markets": observed,
        "public_h2h_consensus_event_count": count if observed_h2h else 0,
        "missing_markets": [market for market in MARKETS if market not in observed],
        "market_coverage_complete": False,
        "handicap_available": False,
        "totals_available": False,
        "spread_lines_authenticated": False,
        "totals_lines_authenticated": False,
        "public_consensus_is_not_executable_quote": True,
        "public_artifact_timestamps_independently_authenticated": False,
        "requested_does_not_mean_collected": True,
        "raw_prices_verified": False,
        "can_recommend_handicap_or_totals": False,
        "reason": reason,
        "production_recommendations": "DISABLED",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", default="market/latest.json")
    parser.add_argument("--summary", default="market/private_summary_latest.json")
    parser.add_argument("--output", default="market/coverage_audit.json")
    args = parser.parse_args()
    report = audit(json.loads(Path(args.market).read_text(encoding="utf-8")),
                   json.loads(Path(args.summary).read_text(encoding="utf-8")))
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"missing_markets": report["missing_markets"],
                      "status": report["status"],
                      "production_recommendations": "DISABLED"}))


if __name__ == "__main__":
    main()
