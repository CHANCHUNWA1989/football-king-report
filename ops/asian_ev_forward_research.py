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
    """Research ROI for evidence-bearing, pre-match, independent fixtures only.

    Conservative default: one evaluated selection per fixture. This avoids
    overstating sample size from correlated bets or multiple quote snapshots.
    In-play settlement is deliberately unsupported.
    """
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    seen_fixtures = set()
    seen_quotes = set()
    seen_predictions = set()
    profits, predicted, records = [], [], []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_ROW")
        evidence = validate_historical_price(row)
        if row["market_phase"] != "PREMATCH":
            raise ValueError("INPLAY_ROI_NOT_SUPPORTED")
        if row["settlement_basis"] != "FULL_MATCH":
            raise ValueError("REMAINDER_SETTLEMENT_NOT_SUPPORTED")
        quote_key = (row["provider"], row["provider_quote_id"])
        if quote_key in seen_quotes:
            raise ValueError("DUPLICATE_PROVIDER_QUOTE")
        seen_quotes.add(quote_key)
        fixture = row["fixture_id"]
        if fixture in seen_fixtures:
            raise ValueError("MULTIPLE_SELECTIONS_PER_FIXTURE")
        seen_fixtures.add(fixture)
        for field in ("model_version", "prediction_id"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError("MISSING_" + field.upper())
        if row["prediction_id"] in seen_predictions:
            raise ValueError("DUPLICATE_PREDICTION_ID")
        seen_predictions.add(row["prediction_id"])
        prediction_time, decision, kickoff, settled = (_utc(row.get(k)) for k in
            ("prediction_created_utc", "decision_utc", "kickoff_utc", "settlement_utc"))
        quote_time = _utc(row["quote_utc"])
        if not prediction_time <= quote_time <= decision:
            raise ValueError("PREDICTION_QUOTE_ORDER_INVALID")
        if (decision - prediction_time).total_seconds() > 86400:
            raise ValueError("STALE_PREDICTION")
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
            "fixture_id": fixture,
            "provider_quote_id": evidence["provider_quote_id"],
            "prediction_id": row["prediction_id"],
            "model_version": row["model_version"],
            "net_units": profit,
        })
    n = len(profits)
    return {
        "sample_count": n,
        "unique_fixture_count": len(seen_fixtures),
        "total_net_units": sum(profits),
        "roi_per_unit": sum(profits) / n if n else None,
        "mean_predicted_ev": sum(predicted) / n if n else None,
        "records": records,
        "evidence_independently_verified": False,
        "calibrated": False,
        "positive_ev_verified": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
