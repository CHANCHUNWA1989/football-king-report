"""Conservative EV screening; research candidates only."""
import math

def screen_ev(odds, probability, *, calibrated=False, fresh_odds=False, minimum_ev=0.05):
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (odds,probability,minimum_ev)):
        raise ValueError("INVALID_NUMERIC_INPUT")
    if odds<=1 or not 0<=probability<=1 or minimum_ev<0:
        raise ValueError("INVALID_RANGE")
    ev=odds*probability-1
    blockers=[]
    if not calibrated: blockers.append("UNCALIBRATED_PROBABILITY")
    if not fresh_odds: blockers.append("UNVERIFIED_ODDS_FRESHNESS")
    if ev<minimum_ev: blockers.append("INSUFFICIENT_EV")
    return {"ev":round(ev,6),"break_even_probability":round(1/odds,6),
            "research_candidate":not blockers,"blockers":blockers,
            "production_recommendations":"DISABLED"}
