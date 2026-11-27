"""Offline prematch snapshot diagnostic; never authenticates prices or releases tips.

All rates are explicit uncalibrated research assumptions, not measured xG.
No source authentication, network, execution or production changes.
"""
from datetime import datetime, timezone
from math import isfinite
from .research_multimodel_v1 import score_matrix, probabilities
from .research_asian_settlement_v1 import asian_ev

KEYS = ("home", "draw", "away")
MAX_AGE_SECONDS = 300
STRESS = 0.15
GAP_ALERT = 0.15

def _time(value):
    if not isinstance(value, str):
        raise ValueError("timestamp required")
    t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError("timezone required")
    return t.astimezone(timezone.utc)

def _number(value, lo, hi):
    if type(value) not in (int, float) or not isfinite(value) or not lo <= value <= hi:
        raise ValueError("invalid numeric input")
    return float(value)

def _odds(value):
    x = _number(value, 1, 1000)
    if x <= 1:
        raise ValueError("decimal odds must exceed one")
    return x

def audit(*, fixture_id, kickoff, as_of, quote_at, rates_at, odds, rates, asian=()):
    """Prematch scenario diagnostic; no executable or certified EV.
    Asian quotes must share the supplied snapshot time, and use home handicap convention.
    Caller labels and timestamps are untrusted; even successful checks are structural only.
    """
    out = {"schema": "unified-snapshot-audit-v1", "status": "HOLD",
           "production_recommendations": "DISABLED", "certified_ev": False,
           "source_authenticity_verified": False, "independent_oos_proven": False,
           "model_promotion_allowed": False}
    try:
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise ValueError("fixture ID required")
        k, now, q, r = map(_time, (kickoff, as_of, quote_at, rates_at))
        if not (q <= now < k and r <= now):
            raise ValueError("future or post-kickoff data")
        if (now-q).total_seconds() > MAX_AGE_SECONDS:
            raise ValueError("stale snapshot")
        if not isinstance(odds, dict) or set(odds) != set(KEYS):
            raise ValueError("complete 1X2 required")
        prices = {key: _odds(odds[key]) for key in KEYS}
        implied = {key: 1/v for key,v in prices.items()}
        mass = sum(implied.values())
        market = {key: v/mass for key,v in implied.items()}
        if not isinstance(rates, (tuple,list)) or len(rates) != 2:
            raise ValueError("two rates required")
        h,a = (_number(v, 0.01, 10/(1+STRESS)) for v in rates)
        matrices = [score_matrix(h,a)]
        # Full independent stress grid; diagonal cases affect totals and BTTS.
        matrices += [score_matrix(h*(1+x),a*(1+y)) for x in (-STRESS,0,STRESS)
                     for y in (-STRESS,0,STRESS) if (x,y)!=(0,0)]
        ps = [probabilities(m) for m in matrices]
        base = ps[0]
        rows = {}
        for key in KEYS:
            lo, hi = min(p[key] for p in ps), max(p[key] for p in ps)
            rows[key] = {"market_probability": market[key], "fair_market_odds": 1/market[key],
                         "break_even": implied[key], "scenario_probability": base[key],
                         "scenario_probability_range": [lo,hi],
                         "hypothetical_ev": prices[key]*base[key]-1,
                         "hypothetical_ev_range": [prices[key]*lo-1,prices[key]*hi-1],
                         "large_market_gap": abs(base[key]-market[key]) >= GAP_ALERT}
        if not isinstance(asian, (tuple,list)) or len(asian)>12:
            raise ValueError("invalid Asian markets")
        asian_rows = []
        for quote in asian:
            if not isinstance(quote, dict) or set(quote)!={"market","selection","line","decimal_odds"}:
                raise ValueError("invalid Asian quote schema")
            results = [asian_ev(m, **quote) for m in matrices]
            evs = [x["expected_net_return"] for x in results]
            asian_rows.append({"base":results[0],"hypothetical_ev_range":[min(evs),max(evs)]})
        def goal_metrics(m):
            return {"over_2_5":sum(v for i,row in enumerate(m) for j,v in enumerate(row) if i+j>=3),
                    "both_score":sum(v for i,row in enumerate(m) for j,v in enumerate(row) if i>0 and j>0)}
        goals = [goal_metrics(m) for m in matrices]
        return {**out,"structural_audit_passed":True,"fixture_id":fixture_id,
                "quote_age_seconds":(now-q).total_seconds(),"rates_age_seconds":(now-r).total_seconds(),
                "overround":mass-1,"one_x_two":rows,"asian":asian_rows,
                "goal_scenarios":{key:{"base":goals[0][key],"range":[min(g[key] for g in goals),max(g[key] for g in goals)]}
                                  for key in goals[0]},
                "scenario_count":len(matrices),"rate_kind":"UNCALIBRATED_ASSUMPTION",
                "thresholds":{"max_quote_age_seconds":MAX_AGE_SECONDS,"stress":STRESS,"gap_alert":GAP_ALERT}}
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
        return {**out,"structural_audit_passed":False,"reason":"INVALID_STALE_OR_POST_KICKOFF_INPUT"}
