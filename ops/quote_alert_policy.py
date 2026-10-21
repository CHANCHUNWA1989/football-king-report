"""Research-only material quote movement alert decision.

The caller supplies independently acquired quote snapshots. This module
does not fetch odds, verify execution, infer EV, or send notifications.
"""
from math import isfinite
from ops.quote_snapshot_compare import compare_quotes

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def evaluate_quote_alert(previous_raw, current_raw, *,
                         previous_captured_utc, current_captured_utc,
                         minimum_odds_change=0.05):
    if (type(minimum_odds_change) not in (int, float)
            or not isfinite(minimum_odds_change)
            or minimum_odds_change <= 0):
        raise ValueError("INVALID_ALERT_THRESHOLD")
    comparison = compare_quotes(
        previous_raw, current_raw,
        previous_captured_utc=previous_captured_utc,
        current_captured_utc=current_captured_utc)
    if comparison["line_changed"]:
        reason = "MARKET_LINE_CHANGED"
    elif abs(comparison["odds_delta_same_line"]) >= minimum_odds_change:
        reason = "MATERIAL_ODDS_CHANGE"
    else:
        reason = "NO_MATERIAL_CHANGE"
    return {
        "notify": reason != "NO_MATERIAL_CHANGE",
        "reason": reason,
        "fixture_id": comparison["fixture_id"],
        "market": comparison["market"],
        "selection": comparison["selection"],
        "provider": comparison["provider"],
        "bookmaker": comparison["bookmaker"],
        "previous_quote_utc": comparison["previous_quote_utc"],
        "current_quote_utc": comparison["current_quote_utc"],
        "previous_line": comparison["previous_line"],
        "current_line": comparison["current_line"],
        "previous_decimal_odds": comparison["previous_decimal_odds"],
        "current_decimal_odds": comparison["current_decimal_odds"],
        "odds_delta_same_line": comparison["odds_delta_same_line"],
        "quote_authenticity_verified": False,
        "calibrated_positive_ev": False,
        "production_recommendations": PRODUCTION_RECOMMENDATIONS,
    }
