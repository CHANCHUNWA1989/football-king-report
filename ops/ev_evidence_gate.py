"""Conservative research-only 1X2 EV evidence gate.

Never treat market-implied probabilities as independent model calibration.
Does not authorize production bets or handle Asian handicap settlement.
"""
import math
from datetime import datetime, timezone

def _time(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt.astimezone(timezone.utc)

def audit_1x2(quote, forecast, *, min_ev=0.05, max_quote_age_minutes=60):
    """Return HOLD unless all independent evidence is present and time-valid.

    quote: {decimal_odds, captured_utc, market_updated_utc, kickoff_utc,
            source, executable}
    forecast: {probability, prediction_utc, calibrated, independent_of_market,
               out_of_sample_verified}
    """
    result = {"status": "HOLD", "production_recommendations": "DISABLED",
              "qualifies_for_research": False, "reason": "INVALID_EVIDENCE",
              "ev": None, "fair_odds": None}
    try:
        odds, p = quote["decimal_odds"], forecast["probability"]
        if type(odds) not in (int, float) or type(p) not in (int, float):
            raise ValueError("invalid number")
        if not (math.isfinite(odds) and odds > 1 and math.isfinite(p) and 0 < p < 1):
            raise ValueError("invalid range")
        updated, captured, predicted, kickoff = map(_time, (
            quote["market_updated_utc"], quote["captured_utc"],
            forecast["prediction_utc"], quote["kickoff_utc"]))
        if not (updated <= captured <= predicted < kickoff):
            result["reason"] = "CHRONOLOGY_FAILURE"
            return result
        if (captured-updated).total_seconds() > max_quote_age_minutes*60:
            result["reason"] = "STALE_QUOTE"
            return result
        if not quote.get("source") or quote.get("executable") is not True:
            result["reason"] = "UNVERIFIED_EXECUTABLE_PRICE"
            return result
        if not all(forecast.get(k) is True for k in (
                "calibrated", "independent_of_market", "out_of_sample_verified")):
            result["reason"] = "MODEL_EVIDENCE_MISSING"
            return result
        ev = p*odds-1
        result.update(ev=round(ev, 6), fair_odds=round(1/p, 6))
        result["reason"] = "EV_BELOW_THRESHOLD" if ev < min_ev else "RESEARCH_THRESHOLD_MET"
        result["qualifies_for_research"] = ev >= min_ev
        result["status"] = "RESEARCH_ONLY"
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError):
        pass
    return result
