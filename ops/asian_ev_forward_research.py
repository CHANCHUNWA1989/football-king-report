"""Research-only forward EV evaluation from sealed, settled selections.

Requires traceable historical quote evidence for every record. A provider's
self-reported executable flag is NOT independent verification. No production
recommendations or certified positive EV are produced.
"""
from math import isfinite
from datetime import datetime, timezone
from ops.asian_ev_research import asian_net
from ops.historical_odds_evidence import validate_historical_price

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("INVALID_TIME") from None
    if dt.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return dt.astimezone(timezone.utc)

def evaluate_settled(rows):
    """Research ROI for unique, evidence-bearing pre-match settled rows only.

    In-play markets are deliberately excluded until full-match versus
    remaining-match outcome settlement is independently verified.
    """
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    seen = set()
    profits, predicted, records = [], [], []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_ROW")
        evidence = validate_historical_price(row)
        if row["market_phase"] != "PREMATCH":
            raise ValueError("INPLAY_ROI_NOT_SUPPORTED")
        key = (row["fixture_id"], row["market"], row["selection"],
               row["quote_utc"], row["provider_quote_id"])
        if key in seen:
            raise ValueError("DUPLICATE_QUOTE")
        seen.add(key)
        decision, kickoff, settled = (_utc(row.get(k)) for k in
            ("decision_utc", "kickoff_utc", "settlement_utc"))
        if not decision < kickoff < settled:
            raise ValueError("INVALID_FORWARD_CHRONOLOGY")
        if type(row.get("margin")) is not int:
            raise ValueError("INVALID_MARGIN")
        ev = row.get("model_ev")
        if type(ev) not in (float, int) or not isfinite(ev):
            raise ValueError("INVALID_MODEL_EV")
        profit = asian_net(row["margin"], row.get("line"), row["decimal_odds"])
        profits.append(profit)
        predicted.append(ev)
        records.append({
            "fixture_id": row["fixture_id"],
            "provider_quote_id": evidence["provider_quote_id"],
            "net_units": profit,
        })
    n = len(profits)
    return {
        "sample_count": n,
        "total_net_units": sum(profits),
        "roi_per_unit": sum(profits) / n if n else None,
        "mean_predicted_ev": sum(predicted) / n if n else None,
        "records": records,
        "evidence_independently_verified": False,
        "calibrated": False,
        "positive_ev_verified": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
