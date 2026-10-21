"""Research-only forward EV evaluation from sealed, settled selections.

Never estimates missing executable prices or promotes betting recommendations.
Input rows must be prevalidated upstream for identity, timing, settlement basis,
and non-leaking probability estimates.
"""
from math import isfinite
from ops.asian_ev_research import asian_net

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def evaluate_settled(rows):
    """Summarize strictly sealed pre-event predictions and settled outcomes.

    Required: unique fixture_id+market+selection+quote_utc, decision_utc,
    kickoff_utc, settlement_utc, margin, line, decimal_odds, model_ev.
    All times are timezone-aware ISO-8601; predictions must predate kickoff.
    """
    from datetime import datetime, timezone
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    seen = set()
    profits, predicted, records = [], [], []
    def parse(value):
        if not isinstance(value, str):
            raise ValueError("INVALID_TIME")
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("INVALID_TIME") from None
        if dt.tzinfo is None:
            raise ValueError("NAIVE_TIME")
        return dt.astimezone(timezone.utc)
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_ROW")
        key = tuple(row.get(k) for k in ("fixture_id", "market", "selection", "quote_utc"))
        if any(not isinstance(x, str) or not x.strip() for x in key) or key in seen:
            raise ValueError("MISSING_OR_DUPLICATE_IDENTITY")
        seen.add(key)
        quote, decision, kickoff, settled = (parse(row.get(k)) for k in
            ("quote_utc", "decision_utc", "kickoff_utc", "settlement_utc"))
        if not quote <= decision < kickoff < settled:
            raise ValueError("INVALID_FORWARD_CHRONOLOGY")
        if type(row.get("margin")) is not int:
            raise ValueError("INVALID_MARGIN")
        ev = row.get("model_ev")
        if type(ev) not in (float, int) or not isfinite(ev):
            raise ValueError("INVALID_MODEL_EV")
        profit = asian_net(row["margin"], row.get("line"), row.get("decimal_odds"))
        profits.append(profit)
        predicted.append(ev)
        records.append({"fixture_id": row["fixture_id"], "net_units": profit})
    n = len(profits)
    return {
        "sample_count": n,
        "total_net_units": sum(profits),
        "roi_per_unit": sum(profits)/n if n else None,
        "mean_predicted_ev": sum(predicted)/n if n else None,
        "records": records,
        "calibrated": False,
        "positive_ev_verified": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
