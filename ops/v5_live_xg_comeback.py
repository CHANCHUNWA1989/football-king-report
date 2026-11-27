"""V5 phase 6: single-dismissal regulation-time scenario distribution.
No live collector, calibrated card effects, authentic provider proof or betting.
Only data observed and captured by the prediction clock may enter.
"""
import math
from datetime import datetime, timezone
from ops.red_card_forward_evidence import agree, stamp, ident, number, score

MODEL="v5-live-xg-shrinkage-scenario-v1"
PRIOR_SECONDS=1800
MAX_AGE=90
CARD_DOWN=.75
CARD_UP=1.25

def require(ok, reason):
    if not ok:raise ValueError(reason)

def clock(v):
    require(type(v) is int and 0<=v<5400,"UNSUPPORTED_REGULATION_CLOCK")
    return v

def base_state(a,b,now):
    for d in (a,b):
        require(isinstance(d,dict) and d["phase"] in ("FIRST_HALF","SECOND_HALF")
                and d["clock_kind"]=="REGULATION_SECONDS_NO_STOPPAGE","UNSUPPORTED_PHASE")
        for k in ("fixture_id","publisher_id","origin_group"):ident(d[k])
        c=clock(d["clock_s"])
        require((d["phase"]=="FIRST_HALF" and c<2700) or
                (d["phase"]=="SECOND_HALF" and c>=2700),"PHASE_CLOCK_CONFLICT")
        score(d["score"])
        reds=d["reds"]
        require(isinstance(reds,list) and len(reds)==2 and all(type(x) is int and 0<=x<=1 for x in reds)
                and sum(reds)<=1,"MULTIPLE_CARDS_UNSUPPORTED")
        k,o,t=(stamp(d[x]) for x in ("kickoff_utc","observed_utc","captured_utc"))
        require(k<=o<=t<=now and (now-o).total_seconds()<=MAX_AGE
                and (o-k).total_seconds()>=c,"STALE_OR_INCONSISTENT_STATE")
    require(a["role"]=="OFFICIAL" and b["role"]=="INDEPENDENT","BAD_ROLES")
    require(a["publisher_id"].casefold()!=b["publisher_id"].casefold() and
            a["origin_group"].casefold()!=b["origin_group"].casefold(),"SHARED_SOURCE")
    for k in ("fixture_id","phase","clock_kind","clock_s","score","reds"):
        require(a[k]==b[k],"STATE_CONFLICT_"+k.upper())
    for k in ("kickoff_utc","observed_utc"):
        require(stamp(a[k])==stamp(b[k]),"STATE_TIME_CONFLICT")
    return a

def prior_rates(prior,s):
    require(prior["fixture_id"]==s["fixture_id"],"PRIOR_FIXTURE_CONFLICT")
    require(stamp(prior["training_cutoff_utc"])<=stamp(prior["prediction_utc"])<
            stamp(s["kickoff_utc"]),"PRIOR_TIME_LEAKAGE")
    require(prior["rate_kind"]=="FULL_REGULATION_GOAL_EXPECTATION","BAD_PRIOR_RATE_KIND")
    ident(prior["model_id"])
    return [number(prior[k],.05,5.5) for k in ("home_goals_expected","away_goals_expected")]

def card_clock(s,official,independent,now):
    if sum(s["reds"])==0:
        require(official is None and independent is None,"UNEXPECTED_CARD_INPUT")
        return 0
    require(official is not None and independent is not None,"CARD_EVIDENCE_REQUIRED")
    a,b=agree(official,independent)
    require(a["fixture_id"]==s["fixture_id"] and
            stamp(a["kickoff_utc"])==stamp(s["kickoff_utc"]),"CARD_FIXTURE_CONFLICT")
    require(a["side"]==("HOME" if s["reds"][0] else "AWAY"),"CARD_SIDE_CONFLICT")
    require(a["clock_s"]<=s["clock_s"] and stamp(a["event_utc"])<=stamp(s["observed_utc"])
            and max(stamp(a["captured_utc"]),stamp(b["captured_utc"]))<=now,"CARD_TIME_LEAKAGE")
    require(all(x<=y for x,y in zip(score(a["score"]),score(s["score"]))),"CARD_SCORE_CONFLICT")
    return a["clock_s"]

def xg_window(s,snapshots,card,now):
    require(isinstance(snapshots,list) and len(snapshots)==2,"TWO_XG_SNAPSHOTS_REQUIRED")
    a,b=snapshots
    for d in snapshots:
        require(d["fixture_id"]==s["fixture_id"],"XG_FIXTURE_CONFLICT")
        for k in ("publisher_id","xg_model"):ident(d[k])
        clock(d["clock_s"])
        o,t=(stamp(d[k]) for k in ("observed_utc","captured_utc"))
        require(stamp(s["kickoff_utc"])<=o<=t<=now and o<=stamp(s["observed_utc"]),"XG_TIME_LEAKAGE")
    require(all(a[k]==b[k] for k in ("publisher_id","xg_model")),"XG_MODEL_CHANGED")
    require(card<=a["clock_s"]<b["clock_s"]==s["clock_s"] and
            stamp(a["observed_utc"])<stamp(b["observed_utc"])==stamp(s["observed_utc"]) and
            stamp(a["captured_utc"])<=stamp(b["observed_utc"]),"XG_CLOCK_OR_CARD_BOUNDARY")
    exposure=b["clock_s"]-a["clock_s"]
    require(300<=exposure<=1800,"XG_WINDOW_OUTSIDE_RANGE")
    first=[number(a[k],0,30) for k in ("home_xg","away_xg")]
    last=[number(b[k],0,30) for k in ("home_xg","away_xg")]
    require(all(x<=y for x,y in zip(first,last)),"XG_DECREASED")
    return exposure,[y-x for x,y in zip(first,last)]

def poisson(rate):
    p=[math.exp(-rate)]
    for i in range(1,41):p.append(p[-1]*rate/i)
    return p

def distribution(h,a,rh,ra):
    score([h,a])
    rh,ra=number(rh,0,8),number(ra,0,8)
    p=[0.,0.,0.];totals={};margins={}
    for i,x in enumerate(poisson(rh)):
        for j,y in enumerate(poisson(ra)):
            w=x*y;d=h+i-a-j;t=h+a+i+j
            p[0 if d>0 else 1 if d==0 else 2]+=w
            totals[t]=totals.get(t,0.)+w
            margins[d]=margins.get(d,0.)+w
    mass=sum(p)
    return {"1x2":[v/mass for v in p],"final_total_p":{str(k):v/mass for k,v in totals.items()},
            "final_margin_p":{str(k):v/mass for k,v in margins.items()},
            "trailing_side":"HOME" if h<a else "AWAY" if a<h else None,
            "trailing_team_final_draw_p":p[1]/mass if h!=a else None,
            "trailing_team_final_win_p":p[0 if h<a else 2]/mass if h!=a else None}

def predict(official_state,independent_state,prior,xg,*,official_card=None,independent_card=None,now=None):
    now=now or datetime.now(timezone.utc)
    require(isinstance(now,datetime) and now.utcoffset() is not None,"BAD_RUNTIME_CLOCK")
    out={"model_id":MODEL,"status":"HOLD","production_recommendations":"DISABLED",
         "promotion_allowed":False,"calibrated":False,"source_authenticity_verified":False,
         "actual_xg_verified":False,"stoppage_time_modelled":False,"distribution":None}
    try:
        s=base_state(official_state,independent_state,now)
        rates=prior_rates(prior,s)
        c=card_clock(s,official_card,independent_card,now)
        exposure,delta=xg_window(s,xg,c,now)
        factors=[CARD_DOWN if s["reds"][0] else CARD_UP if s["reds"][1] else 1.,
                 CARD_DOWN if s["reds"][1] else CARD_UP if s["reds"][0] else 1.]
        remaining=5400-s["clock_s"]
        # Only the prior component is card-adjusted. Observed post-card xG is
        # not multiplied again. The fixed factors and shrinkage are hypothetical.
        rh,ra=[(r*f*PRIOR_SECONDS/5400+x)/(PRIOR_SECONDS+exposure)*remaining
               for r,f,x in zip(rates,factors,delta)]
        dist=distribution(*s["score"],rh,ra)
        out.update(reason="UNVERIFIED_SCENARIO_ONLY",fixture_id=s["fixture_id"],
                   prediction_utc=now.isoformat(),clock_s=s["clock_s"],
                   remaining_regulation_seconds=remaining,remaining_goal_rates=[rh,ra],
                   xg_window_seconds=exposure,distribution=dist)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as e:
        out["reason"]="INVALID_OR_MISSING_INPUT"
        # Never echo arbitrary payloads or provider secrets into diagnostics.
    return out
