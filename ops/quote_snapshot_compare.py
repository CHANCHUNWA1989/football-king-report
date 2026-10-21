"""Research-only comparisons of normalized bookmaker quote snapshots.

Compare only matching provider/bookmaker/fixture/market/selection/line.
A changed line is a distinct market; never describe it as a price movement.
No feed access or verified positive-EV assertion is provided here.
"""
from datetime import datetime
from ops.free_odds_intake import normalize_quote

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def compare_quotes(previous_raw, current_raw, *, previous_captured_utc,
                   current_captured_utc):
    previous = normalize_quote(previous_raw, captured_utc=previous_captured_utc)
    current = normalize_quote(current_raw, captured_utc=current_captured_utc)
    keys = ("provider", "bookmaker", "fixture_id", "market", "selection")
    if any(previous[k] != current[k] for k in keys):
        raise ValueError("DIFFERENT_QUOTE_MARKET")
    if current["quote_utc"] <= previous["quote_utc"]:
        raise ValueError("NON_INCREASING_PROVIDER_TIME")
    if current["captured_utc"] <= previous["captured_utc"]:
        raise ValueError("NON_INCREASING_CAPTURE_TIME")
    if current["provider_quote_id"] == previous["provider_quote_id"]:
        raise ValueError("REUSED_QUOTE_ID")
    same_line = previous["line"] == current["line"]
    odds_delta = round(current["decimal_odds"] - previous["decimal_odds"], 6) if same_line else None
    return {
        "fixture_id": current["fixture_id"],
        "provider": current["provider"],
        "bookmaker": current["bookmaker"],
        "market": current["market"],
        "selection": current["selection"],
        "previous_quote_utc": previous["quote_utc"],
        "current_quote_utc": current["quote_utc"],
        "previous_captured_utc": previous["captured_utc"],
        "current_captured_utc": current["captured_utc"],
        "previous_line": previous["line"],
        "current_line": current["line"],
        "line_changed": not same_line,
        "previous_decimal_odds": previous["decimal_odds"],
        "current_decimal_odds": current["decimal_odds"],
        "odds_delta_same_line": odds_delta,
        "material_change_observed": not same_line or odds_delta != 0,
        "quote_authenticity_verified": False,
        "calibrated_positive_ev": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
