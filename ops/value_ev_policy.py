"""Strict research-only value screening. Never authorize betting from caller claims.

The public pipeline has no independently calibrated probabilities or verified
executable bookmaker quotes. A mathematical positive edge alone is not proof
of positive expected value in real betting.
"""
import math

SCHEMA="football-king-value-screen-v1"
DEFAULT_MIN_DECIMAL_ODDS=1.80
DEFAULT_MIN_CONSERVATIVE_EV=0.03
MAX_QUOTE_AGE_SECONDS=120


def _number(value, lo, hi):
    return type(value) in (int,float) and math.isfinite(value) and lo<=value<=hi


def evaluate(probability, decimal_odds, *, conservative_probability=None,
             quote_age_seconds=None,
             minimum_decimal_odds=DEFAULT_MIN_DECIMAL_ODDS,
             minimum_conservative_ev=DEFAULT_MIN_CONSERVATIVE_EV):
    """Screen a candidate; cannot confer independent proof or recommendation.

    EV = probability * decimal_odds - 1.
    Require a conservative probability bound, fresh observed price, odds floor,
    and a positive EV buffer before even a research-level value-screen pass.
    This is not a bookmaker quote authenticator or model calibration verifier.
    """
    if not _number(minimum_decimal_odds,1.01,100) or not _number(
            minimum_conservative_ev,0,1):
        raise ValueError("INVALID_EV_POLICY")
    result={
        "schema":SCHEMA,
        "status":"HOLD",
        "reason":"UNKNOWN",
        "minimum_decimal_odds":minimum_decimal_odds,
        "minimum_conservative_ev":minimum_conservative_ev,
        "quote_max_age_seconds":MAX_QUOTE_AGE_SECONDS,
        "break_even_probability":None,
        "raw_model_ev":None,
        "conservative_ev":None,
        "minimum_required_decimal_odds":None,
        "research_value_screen_pass":False,
        "independent_calibration_authenticated":False,
        "executable_quote_authenticated":False,
        "independent_forward_value_validated":False,
        "qualifies_for_recommendation":False,
        "production_recommendations":"DISABLED",
        "recommended_stake":None,
    }
    if not _number(probability,0,1):
        result["reason"]="INVALID_PROBABILITY"
        return result
    if decimal_odds is None:
        result["reason"]="NO_VERIFIED_EXECUTABLE_ODDS"
        return result
    if not _number(decimal_odds,1.01,100):
        result["reason"]="INVALID_DECIMAL_ODDS"
        return result
    result["break_even_probability"]=round(1/decimal_odds,8)
    result["raw_model_ev"]=round(probability*decimal_odds-1,8)
    if decimal_odds<minimum_decimal_odds:
        result["reason"]="ODDS_BELOW_MINIMUM"
        return result
    if not _number(conservative_probability,0,1) or conservative_probability>probability:
        result["reason"]="NO_VALID_CALIBRATION_LOWER_BOUND"
        return result
    result["conservative_ev"]=round(conservative_probability*decimal_odds-1,8)
    if conservative_probability:
        result["minimum_required_decimal_odds"]=round(
            max(minimum_decimal_odds,(1+minimum_conservative_ev)/conservative_probability),6)
    if result["conservative_ev"]<minimum_conservative_ev-1e-10:
        result["reason"]="INSUFFICIENT_CONSERVATIVE_EV"
        return result
    if not _number(quote_age_seconds,0,MAX_QUOTE_AGE_SECONDS):
        result["reason"]="MISSING_OR_STALE_QUOTE"
        return result
    result["status"]="RESEARCH_ONLY"
    result["reason"]="POSITIVE_THEORETICAL_EV_REQUIRES_INDEPENDENT_PROOF"
    result["research_value_screen_pass"]=True
    # Deliberately cannot authenticate its own inputs: no caller Boolean,
    # scorecard, market consensus or model estimate can unlock betting.
    return result
