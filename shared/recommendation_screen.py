"""Research-only recommendation screening. Never authorizes an order."""
import math

def screen_recommendation(system, probability, decimal_odds=None, *,
                          verified_market_data=False, verified_model=False,
                          sample_size=0, minimum_sample=100):
    if system not in ("football", "basketball", "quant") or not isinstance(system, str):
        raise ValueError("unsupported system")
    if type(probability) not in (int, float) or not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("invalid probability")
    if type(sample_size) is not int or sample_size < 0 or type(minimum_sample) is not int or minimum_sample < 1:
        raise ValueError("invalid sample size")
    if type(verified_market_data) is not bool or type(verified_model) is not bool:
        raise ValueError("verification flags must be booleans")
    if decimal_odds is not None and (type(decimal_odds) not in (int, float) or
                                     not math.isfinite(decimal_odds) or decimal_odds <= 1):
        raise ValueError("invalid decimal odds")
    ev = probability * decimal_odds - 1 if decimal_odds is not None else None
    reasons = []
    if not verified_market_data:
        reasons.append("MARKET_DATA_NOT_VERIFIED")
    if not verified_model:
        reasons.append("MODEL_NOT_VERIFIED")
    if sample_size < minimum_sample:
        reasons.append("INSUFFICIENT_SAMPLE")
    if system in ("football", "basketball"):
        if ev is None:
            reasons.append("MISSING_ODDS")
        elif ev < .05:
            reasons.append("EV_BELOW_RESEARCH_THRESHOLD")
    else:
        reasons.append("QUANT_COST_AND_RISK_ASSESSMENT_REQUIRED")
    return {
        "system": system, "estimated_ev": ev,
        "research_candidate": not reasons,
        "reasons": reasons,
        "live_execution_allowed": False,
        "status": "RESEARCH_ONLY",
    }
