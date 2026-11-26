"""Isolated offline live snapshot audit. Research only: never emits recommendations."""
from datetime import datetime, timedelta
from math import isfinite

DEPLOYMENT = "HOLD"
RECOMMENDATIONS = "DISABLED"

def _number(x):
    return type(x) in (int, float) and isfinite(x)

def implied(odds):
    if len(odds) < 2 or any(not _number(x) or x <= 1 for x in odds):
        raise ValueError("invalid decimal odds")
    raw = [1/x for x in odds]
    total = sum(raw)
    return [x/total for x in raw], total-1

def aware(s):
    if not isinstance(s, str):
        raise ValueError("timestamp required")
    t = datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.utcoffset() is None:
        raise ValueError("timezone required")
    return t

def freshness(captured, evaluated, max_seconds=60):
    if not _number(max_seconds) or max_seconds <= 0:
        raise ValueError("invalid freshness limit")
    age = (aware(evaluated)-aware(captured)).total_seconds()
    return 0 <= age <= max_seconds

def legs(line):
    if not _number(line) or abs(line)>30 or line*4 != round(line*4):
        raise ValueError("quarter-line required")
    q = round(line*4)
    return ((q-1)/4,(q+1)/4) if q%2 else (line,line)

def profit(margin, line, odds):
    if not _number(margin) or int(margin)!=margin or not _number(odds) or odds<=1:
        raise ValueError("invalid settlement")
    return sum((odds-1 if margin+x>0 else -1 if margin+x<0 else 0)
               for x in legs(line))/2

def audit(snapshot, evaluated, max_seconds=60):
    reasons=[]
    if not freshness(snapshot["captured_at"], evaluated,max_seconds):
        reasons.append("STALE_OR_FUTURE")
    if snapshot.get("period") not in ("FIRST_HALF","SECOND_HALF"):
        reasons.append("PERIOD_UNVERIFIED")
    minute=snapshot.get("minute")
    if type(minute) is not int or minute<0 or minute>130:
        reasons.append("MINUTE_UNVERIFIED")
    sources=snapshot.get("independent_score_sources",[])
    if not isinstance(sources,list) or len(set(s for s in sources if isinstance(s,str) and s.strip()))<2:
        reasons.append("SCORE_CORROBORATION_MISSING")
    if snapshot.get("market_suspended") is not False:
        reasons.append("MARKET_STATUS_UNVERIFIED")
    p,margin=implied(snapshot["one_x_two"])
    h,d,a=p
    hc,hc_margin=implied(snapshot["three_way_home_plus_one"])
    # In this 3-way handicap H+1 wins if home wins or draws;
    # draw+1 is away by exactly one; away -1 wins by >=2.
    gap=abs(h+d-hc[0])
    if gap>0.05:
        reasons.append("CROSS_MARKET_GAP")
    u15,_=implied(snapshot["over_under_15"])
    u25,_=implied(snapshot["over_under_25"])
    bins=[u15[1],u25[1]-u15[1],u25[0]]
    if min(bins)<0:
        reasons.append("TOTALS_NOT_MONOTONE")
        bins=None
    # Market-implied probabilities are diagnostic only; no calibrated independent prediction.
    return {"deployment":DEPLOYMENT,"recommendations":RECOMMENDATIONS,
            "market_only":True,"positive_ev_verified":False,
            "reasons":reasons,"one_x_two":p,"overround":margin,
            "handicap_overround":hc_margin,"handicap_home_or_draw_gap":gap,
            "totals_bins":bins,"qualified":False}

if __name__=="__main__":
    import json
    # Historical user-provided screenshot, not a current quote or an independent feed.
    fixture={"captured_at":"2026-11-26T22:47:00+08:00","period":"FIRST_HALF",
             "minute":None,"independent_score_sources":[],"market_suspended":None,
             "one_x_two":[5.40,2.80,1.69],"three_way_home_plus_one":[1.93,3.00,3.45],
             "over_under_15":[1.84,1.86],"over_under_25":[3.65,1.23]}
    print(json.dumps(audit(fixture,"2026-11-26T22:47:00+08:00"),indent=2))
