"""Five-grade settlement EV sensitivity, research mathematics only.

The TV radii are hypothetical, NOT estimated calibration confidence bounds.
Input prices and distributions are unauthenticated. No selection, stake,
research pass or production release. Conservative generic five-grade support
may include impossible grades for a specific contract; bound remains safe.
"""
from math import fsum, isfinite

GRADES=("FULL_WIN","HALF_WIN","PUSH","HALF_LOSS","FULL_LOSS")
RADII=(0.,.01,.03,.05,.10)


def _number(x,lo,hi):
    return type(x) in (int,float) and isfinite(x) and lo<=x<=hi


def _adverse(p,payoffs,radius):
    """Exact minimum over a TV ball on generic five-grade support.

    Transfer up to radius of probability mass from highest payoff to
    lowest payoff; TV distance is half the L1 distance.
    """
    q=dict(p)
    low=min(GRADES,key=lambda k:payoffs[k])
    remaining=min(radius,1-q[low])
    for high in sorted(GRADES,key=lambda k:payoffs[k],reverse=True):
        if high==low or remaining<=0:
            break
        move=min(q[high],remaining)
        q[high]-=move
        q[low]+=move
        remaining-=move
    return fsum(q[k]*payoffs[k] for k in GRADES)


def analyze(probabilities,decimal_odds):
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "positive_ev_verified":False,"price_authenticated":False,
         "probability_calibration_authenticated":False,
         "certified_prospective_samples":0,"recommended_stake":None,
         "hypothetical_sensitivity_only":True}
    try:
        if (type(probabilities) is not dict or set(probabilities)!=set(GRADES)
                or any(not _number(v,0,1) for v in probabilities.values())
                or abs(fsum(probabilities.values())-1)>1e-10
                or not _number(decimal_odds,1.01,100)):
            raise ValueError("INVALID_INPUT")
        mass=fsum(probabilities.values())
        p={k:probabilities[k]/mass for k in GRADES}
        gain=p["FULL_WIN"]+.5*p["HALF_WIN"]
        loss=p["FULL_LOSS"]+.5*p["HALF_LOSS"]
        payoffs=dict(zip(GRADES,(decimal_odds-1,(decimal_odds-1)/2,0.,-.5,-1.)))
        nominal=fsum(p[k]*payoffs[k] for k in GRADES)
        return {**out,"reason":"UNAUTHENTICATED_SETTLEMENT_SENSITIVITY",
                "nominal_net_ev_per_unit":nominal,
                "nominal_break_even_decimal_odds":1+loss/gain if gain>0 else None,
                "break_even_undefined_no_win_mass":gain==0,
                "hypothetical_tv_stress":[{"radius":r,
                    "minimum_net_ev_per_unit":_adverse(p,payoffs,r)} for r in RADII],
                "stress_radii_are_empirically_calibrated":False}
    except (ValueError,TypeError,OverflowError,KeyError):
        return {**out,"reason":"INVALID_SETTLEMENT_OR_PRICE"}
