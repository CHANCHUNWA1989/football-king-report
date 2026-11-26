"""Fixed historical full-season deep-margin benchmark, private research only.

No historical offered lines, odds, actual market selection or prospective
evidence. Team-rate challenger uses only frozen first-period match results.
The same hypothetical side and lines are evaluated for both models.
"""
from collections import Counter, defaultdict
from datetime import date
import math
from asian_handicap_research import TYPES, _poisson
from deep_handicap_joint_score import score_distribution, NET_GRADE
from asian_ev_research import asian_net
from deep_handicap_historical_inputs import _id

SCHEMA = "football-king-dhe-league-margin-benchmark-v1"
SPLIT = date(2016,1,1)
START = date(2015,8,1)
END = date(2016,5,31)
LINES = (-1.5,-2.25,-2.5,-3.0)
SHRINK = 5
LEAGUES = {2:(190,190),12:(169,211)}


def parse(matches, competition):
    if type(competition) is not int or competition not in LEAGUES:
        raise ValueError("UNSUPPORTED_COMPETITION")
    if type(matches) is not list or len(matches)!=380:
        raise ValueError("INCOMPLETE_SEASON")
    seen, pairs, teams = set(),set(),set()
    rows=[]
    for m in matches:
        mid=_id(m["match_id"])
        h=_id(m["home_team"]["home_team_id"])
        a=_id(m["away_team"]["away_team_id"])
        day=date.fromisoformat(m["match_date"])
        if (mid in seen or (h,a) in pairs or h==a or not START<=day<=END
                or m["competition"]["competition_id"]!=competition
                or m["season"]["season_id"]!=27 or m["match_status"]!="available"
                or m["competition_stage"]["name"]!="Regular Season"):
            raise ValueError("SEASON_IDENTITY_CONFLICT")
        hg,ag=m["home_score"],m["away_score"]
        if any(type(v) is not int or not 0<=v<=25 for v in (hg,ag)):
            raise ValueError("INVALID_SCORE")
        seen.add(mid)
        pairs.add((h,a))
        teams.update((h,a))
        rows.append((day,mid,h,a,hg,ag))
    if len(teams)!=20 or pairs!={(h,a) for h in teams for a in teams if h!=a}:
        raise ValueError("NOT_FULL_DOUBLE_ROUND_ROBIN")
    rows.sort()
    train=[r for r in rows if r[0]<SPLIT]
    test=[r for r in rows if r[0]>=SPLIT]
    if (len(train),len(test))!=LEAGUES[competition]:
        raise ValueError("CHRONOLOGICAL_COHORT_MISMATCH")
    return train,test


def fit(train):
    """Fit venue-specific attack and defence with fixed shrinkage."""
    n=len(train)
    lh=math.fsum(r[4] for r in train)/n
    la=math.fsum(r[5] for r in train)/n
    if min(lh,la)<=0:
        raise ValueError("ZERO_LEAGUE_RATE")
    stats=defaultdict(lambda:[0,0,0])
    for _,_,h,a,hg,ag in train:
        for k,g,c in (((h,"HOME"),hg,ag),((a,"AWAY"),ag,hg)):
            s=stats[k]
            s[0]+=1
            s[1]+=g
            s[2]+=c
    return lh,la,dict(stats)


def rates(model,h,a):
    lh,la,stats=model
    nh,gh,ch=stats[(h,"HOME")]
    na,ga,ca=stats[(a,"AWAY")]
    if min(nh,na)<5:
        raise ValueError("INSUFFICIENT_TEAM_HISTORY")
    ah=(gh+SHRINK*lh)/(nh+SHRINK)/lh
    dh=(ch+SHRINK*la)/(nh+SHRINK)/la
    aa=(ga+SHRINK*la)/(na+SHRINK)/la
    da=(ca+SHRINK*lh)/(na+SHRINK)/lh
    x,y=lh*ah*da,la*aa*dh
    _poisson(x)
    _poisson(y)
    return x,y


def grade_distributions(h,a,side):
    margin=defaultdict(float)
    for (x,y),p in score_distribution(h,a,side).items():
        margin[x-y if side=="HOME" else y-x]+=p
    result={}
    for line in LINES:
        p=dict.fromkeys(TYPES,0.0)
        for m,w in margin.items():
            p[NET_GRADE[asian_net(m,line,2.0)]]+=w
        if abs(math.fsum(p.values())-1)>1e-9:
            raise ValueError("INVALID_GRADE_MASS")
        result[line]=p
    return result


def evaluate(matches,competition):
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "true_forward_sample_count":0,"actual_market_lines_available":False,
         "positive_expected_value_verified":False,"model_accuracy_verified":False,
         "private_metrics":None,"private_research_only":True}
    try:
        train,test=parse(matches,competition)
        model=fit(train)
        lh,la,_=model
        # Fixed training only: no score from holdout used to fit or select side.
        summaries={line:{"brier_delta":[],"log_delta":[]} for line in LINES}
        evaluated=0
        for _,_,h,a,hg,ag in test:
            x,y=rates(model,h,a)
            side="HOME" if x>=y else "AWAY"
            b=grade_distributions(lh,la,side)
            c=grade_distributions(x,y,side)
            m=hg-ag if side=="HOME" else ag-hg
            for line in LINES:
                actual=NET_GRADE[asian_net(m,line,2.0)]
                q,p=b[line],c[line]
                summaries[line]["brier_delta"].append(
                    math.fsum((p[k]-(k==actual))**2-(q[k]-(k==actual))**2 for k in TYPES))
                summaries[line]["log_delta"].append(
                    math.log(max(1e-15,q[actual]))-math.log(max(1e-15,p[actual])))
            evaluated+=1
        out.update(reason="RETROSPECTIVE_HYPOTHETICAL_MARGIN_ONLY",
                   train_count=len(train),holdout_count=len(test),evaluated_count=evaluated,
                   private_metrics={str(k):{m:math.fsum(v)/evaluated for m,v in s.items()}
                                    for k,s in summaries.items()})
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError,ZeroDivisionError):
        out["reason"]="BENCHMARK_INPUT_OR_RATE_DOMAIN_REJECTED"
    return out
