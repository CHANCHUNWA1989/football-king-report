"""Research-only comparison of model and market probabilities on matched cases."""
from research_quality.probability_diagnostics import score_forecasts

def compare(rows):
    if not isinstance(rows, list) or len(rows) > 20000:
        raise ValueError("INVALID_SAMPLE_COUNT")
    model = []
    market = []
    for row in rows:
        if not isinstance(row, dict) or "m" not in row:
            raise ValueError("MISSING_MARKET_PROBABILITIES")
        model.append({"p": row.get("p"), "y": row.get("y")})
        market.append({"p": row["m"], "y": row.get("y")})
    a = score_forecasts(model)
    b = score_forecasts(market)
    return {"n": len(rows), "model": a, "market": b,
            "market_minus_model_brier": None if not rows else b["brier"] - a["brier"],
            "market_minus_model_log_loss": None if not rows else b["log_loss"] - a["log_loss"],
            "advantage_verified": False, "production_recommendations": "DISABLED"}
