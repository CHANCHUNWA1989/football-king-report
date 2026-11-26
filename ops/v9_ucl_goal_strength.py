"""UCL opponent-adjusted dynamic log-goal strengths, research only.
Country factors use UCL results, not domestic league ratings. Date-only clocks.
All same-day predictions use pre-day states. No current-season forecasts.
"""
import math
from collections import defaultdict
from datetime import date
from ops import v8_ucl_calibration as c,v5_ensemble_competition as e
from ops.v8_ucl_opponent import decayed
from ops.v9_league_weights import ci

CLUB_STEP=.035
COUNTRY_STEP=.012
VENUE_STEP=.008
BOUND=.9
BLENDS=(0.,.25,.5,.75,1.)

def value(state,key,day):
    return decayed(state.get(key,(0.,day)),day)

def clip(x,limit=BOUND):
    return max(-limit,min(limit,x))

def rates(state,h,a,ch,ca,day):
    def side(team,opponent,country,other,venue):
        z=(value(state,("club","attack",team),day)+value(state,("club","defence",opponent),day)
           +value(state,("country","attack",country),day)+value(state,("country","defence",other),day)
           +value(state,("venue",venue),day))
        return max(.1,min(5.5,(1.5 if venue=="home" else 1.2)*math.exp(z)))
    return side(h,a,ch,ca,"home"),side(a,h,ca,ch,"away")

def replay(rows):
    groups=defaultdict(list);seen=set()
    for d,h,a,ch,ca,x,y,season in rows:
        if type(d) is not date or h==a or (d,h,a) in seen or any(type(n) is not int or not 0<=n<=20 for n in (x,y)):
            raise ValueError("UCL_STRENGTH_CASE")
        year=int(season[:4])
        if not date(year,7,1)<=d<date(year+1,7,1):raise ValueError("UCL_STRENGTH_CLOCK")
        seen.add((d,h,a));groups[d].append((d,h,a,ch,ca,x,y,season))
    state={};out=[];prior_n=0
    for day,batch in sorted(groups.items()):
        changes=defaultdict(float)
        for _,h,a,ch,ca,x,y,season in sorted(batch):
            hr,ar=rates(state,h,a,ch,ca,day)
            if prior_n>=96:
                out.append({"date":day.isoformat(),"home":h,"away":a,"season":season,
                            "y":0 if x>y else 1 if x==y else 2,"goal_strength":e.dc(hr,ar),
                            "home_rate":hr,"away_rate":ar})
            # Poisson score residual, clipped for robustness; all updates are
            # applied only after the day's predictions have been generated.
            for team,opp,country,other,venue,actual,pred in (
                (h,a,ch,ca,"home",x,hr),(a,h,ca,ch,"away",y,ar)):
                err=clip(actual-pred,3.)
                for key,step in ((("club","attack",team),CLUB_STEP),
                                 (("club","defence",opp),CLUB_STEP),
                                 (("country","attack",country),COUNTRY_STEP),
                                 (("country","defence",other),COUNTRY_STEP),
                                 (("venue",venue),VENUE_STEP)):
                    changes[key]+=step*err
        for k,delta in changes.items():state[k]=(clip(value(state,k,day)+delta),day)
        prior_n+=len(batch)
    return out

def mix(p,q,w):
    if w not in BLENDS:raise ValueError("UCL_BLEND")
    return e.vec([(1-w)*x+w*y for x,y in zip(e.vec(p),e.vec(q))])

def evaluate(raw,adaptive_rows):
    index={(r["date"],r["home"],r["away"]):r for r in replay(raw)}
    seen=set();rows=[]
    for r in adaptive_rows:
        if r["season"] not in (*c.DEV,c.TEST):continue
        k=(r["date"],r["home"],r["away"]);q=index.get(k)
        if k in seen or q is None or q["season"]!=r["season"] or q["y"]!=r["y"]:raise ValueError("UCL_STRENGTH_PAIR")
        seen.add(k);rows.append({**r,"goal_strength":q["goal_strength"]})
    dev=[r for r in rows if r["season"] in c.DEV];test=[r for r in rows if r["season"]==c.TEST]
    if len(dev)!=336 or len(test)!=144:raise ValueError("UCL_STRENGTH_COHORT")
    # Same development-only calibration grid for both experts.
    old=c.fit([{**r,"hybrid":r["adaptive"]} for r in dev])
    new=c.fit([{**r,"hybrid":r["goal_strength"]} for r in dev])
    def scored(r):
        return {**r,"reference":c.calibrate(r["adaptive"],*old),
                "strength_calibrated":c.calibrate(r["goal_strength"],*new)}
    dev=list(map(scored,dev));test=list(map(scored,test))
    w=min(BLENDS,key=lambda w:(math.fsum(e.loss(mix(r["reference"],r["strength_calibrated"],w),r["y"]) for r in dev)/len(dev)+.005*w*w,w))
    test=[{**r,"candidate":mix(r["reference"],r["strength_calibrated"],w)} for r in test]
    keys=("reference","strength_calibrated","candidate")
    m={k:e.metrics(test,lambda r:r[k]) for k in keys}
    interval=ci([{**r,"hybrid":r["reference"]} for r in test])
    return {"schema":"ucl-dynamic-country-club-goal-strength-research-v1",
        "development_n":len(dev),"assessment_n":len(test),"selected_strength_weight":w,
        "reference_calibration":old,"strength_calibration":new,"metrics":m,
        "class_profiles":{k:c.profile(test,lambda r:r[k]) for k in keys},
        "paired_week_ci_reference_minus_candidate":interval,
        "historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["candidate"][k]<m["reference"][k] for k in ("log_loss","brier"))),
        "country_strength_from_ucl_only":True,"domestic_league_crosswalk_available":False,
        "venue_neutrality_not_known":True,"actual_xg_used":False,"lineups_used":False,
        "assessment_previously_inspected":True,"current_fixture_forecasts":0,
        "verified_forward_sample_credit":0,"automatic_promotion":False,
        "production_recommendations":"DISABLED","status":"HOLD"}
