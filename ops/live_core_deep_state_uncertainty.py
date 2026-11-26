"""Descriptive weekly-block robustness for the fixed retrospective challenger.

Not an independent test: the assessment cohort has already been examined.
All planned league/line/metric comparisons remain in the family.
"""
import json
import math
import random
from collections import defaultdict
from datetime import date
from asian_handicap_research import TYPES,grade
from live_core_deep_halftime_replay import validate,grades
from live_core_deep_state_rates import fit,side,report
from live_core_deep_cross_league import fetch,DISTINCT,SPECS,SEASONS,COVERAGE

METRICS=tuple((line,metric) for line in DISTINCT for metric in ("brier","log_loss"))
FAMILY=24
DRAWS=20000
MIN_ROWS=50
MIN_WEEKS=12
ALPHA=.05

def losses(p,y):
    return math.fsum((p[k]-(k==y))**2 for k in TYPES),-math.log(max(1e-15,p[y]))

def blocks(train,test):
    train,test=validate(train),validate(test)
    if max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("TEMPORAL_OVERLAP")
    pooled,groups=fit(train)
    by_week=defaultdict(list)
    for r in test:
        s=side(r)
        if not s:continue
        day,_,_,i,j,x,y=r
        week=date.fromisoformat(day).isocalendar()[:2]
        v=[]
        for line in DISTINCT:
            ygrade=grade(x,y,s,float(line))
            b=losses(grades(i,j,*pooled,s,float(line),1.),ygrade)
            c=losses(grades(i,j,*groups[s]["rates"],s,float(line),1.),ygrade)
            v.extend(q-p for p,q in zip(b,c))
        by_week[week].append(v)
    return [(len(v),tuple(math.fsum(r[i] for r in v) for i in range(len(METRICS))))
            for _,v in sorted(by_week.items())]

def intervals(weekly):
    if not isinstance(weekly,list) or len(weekly)>60:raise ValueError("BLOCK_SCOPE")
    for n,v in weekly:
        if type(n) is not int or n<=0 or len(v)!=len(METRICS):
            raise ValueError("BLOCK_SHAPE")
        if any(type(x) not in (int,float) or not math.isfinite(x) for x in v):
            raise ValueError("BLOCK_METRIC")
    n=sum(k for k,_ in weekly)
    if n>380:raise ValueError("BLOCK_SCOPE")
    w=len(weekly)
    totals=[math.fsum(v[i] for _,v in weekly) for i in range(len(METRICS))]
    adequate=n>=MIN_ROWS and w>=MIN_WEEKS
    samples=[[] for _ in METRICS]
    if adequate:
        rng=random.Random(20261127)
        for _ in range(DRAWS):
            chosen=[weekly[rng.randrange(w)] for _ in range(w)]
            denom=sum(k for k,_ in chosen)
            for i,out in enumerate(samples):
                out.append(math.fsum(v[i] for _,v in chosen)/denom)
    result={}
    tail=ALPHA/(2*FAMILY)
    for i,(line,metric) in enumerate(METRICS):
        point=totals[i]/n if n else None
        ci=loo=None
        if adequate:
            v=sorted(samples[i])
            ci=[v[max(0,math.floor(tail*DRAWS)-1)],v[min(DRAWS-1,math.ceil((1-tail)*DRAWS))]]
            omitted=[(totals[i]-vals[i])/(n-k) for k,vals in weekly]
            loo=[min(omitted),max(omitted)]
        result.setdefault(line,{})[metric]={"candidate_minus_baseline":point,
             "adjusted_descriptive_interval":ci,"leave_one_week_out_range":loo,
             "direction":"INSUFFICIENT_COVERAGE" if ci is None else
             "LOWER_ERROR_INTERVAL" if ci[1]<0 else "HIGHER_ERROR_INTERVAL" if ci[0]>0 else "INCONCLUSIVE"}
    return {"n":n,"week_blocks":w,"bootstrap_draws":DRAWS if adequate else 0,
            "descriptive_coverage_eligible":adequate,"metrics":result}

def assess(train,test):
    result=intervals(blocks(train,test))
    reference=report(train,test)
    if result["n"]!=reference["eligible_n"]:raise ValueError("COHORT_COUNT")
    for line,metric in METRICS:
        a=result["metrics"][line][metric]["candidate_minus_baseline"]
        b=reference["by_hypothetical_line"][line]["state_minus_baseline"][metric]
        if (a is None)!=(b is None) or (a is not None and abs(a-b)>1e-12):
            raise ValueError("POINT_ESTIMATE_MISMATCH")
    return result

def run():
    leagues={}
    for k in SPECS:
        train,test=fetch(k,SEASONS[0]),fetch(k,SEASONS[1])
        if (len(train),len(test))!=COVERAGE[k]:raise ValueError("COVERAGE")
        leagues[k]=assess(train,test)
    counts={k:0 for k in ("LOWER_ERROR_INTERVAL","HIGHER_ERROR_INTERVAL","INCONCLUSIVE","INSUFFICIENT_COVERAGE")}
    for r in leagues.values():
        for line,metric in METRICS:counts[r["metrics"][line][metric]["direction"]]+=1
    if sum(counts.values())!=FAMILY:raise ValueError("FAMILY_ACCOUNTING")
    return {"schema":"football-king-deep-state-uncertainty-v1","leagues":leagues,
            "planned_comparisons":FAMILY,"direction_counts":counts,"family_alpha":ALPHA,
            "individual_nominal_level":1-ALPHA/FAMILY,
            "method":"BONFERRONI_PERCENTILE_WEEK_BLOCK_BOOTSTRAP",
            "minimum_rows_per_league":MIN_ROWS,"minimum_weeks":MIN_WEEKS,
            "retrospective_exploratory_only":True,"coverage_guaranteed":False,
            "independent_prospective_validation":False,"verified_forward_sample_credit":0,
            "positive_ev_verified":False,"automatic_promotion":False,
            "production_recommendations":"DISABLED","status":"HOLD"}

if __name__=="__main__":print(json.dumps(run(),sort_keys=True,allow_nan=False))
