"""Research-only evidence gate combining source freshness and recommendation screening.

No order routing, sportsbook, broker, or live trading integration.
"""
from .source_freshness import check_source
from .recommendation_screen import screen_recommendation

def evaluate_evidence(*, system, probability, source, observed_at, now,
                      decimal_odds=None, verified_model=False, verified_market_data=False,
                      sample_size=0, max_age_seconds=300):
    freshness = check_source(source, observed_at, now, max_age_seconds)
    recommendation = screen_recommendation(
        system, probability, decimal_odds,
        verified_market_data=(freshness["verified_freshness"] and verified_market_data),
        verified_model=verified_model, sample_size=sample_size)
    return {
        "system": system,
        "source": freshness["source"],
        "age_seconds": freshness["age_seconds"],
        "estimated_ev": recommendation["estimated_ev"],
        "research_candidate": recommendation["research_candidate"],
        "reasons": list(dict.fromkeys(freshness["reasons"] + recommendation["reasons"])),
        "status": "RESEARCH_ONLY",
        "live_execution_allowed": False,
    }
