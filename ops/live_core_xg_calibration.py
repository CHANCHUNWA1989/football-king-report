"""Chronological in-play xG residual calibration experiment.

Each row is a claimed archived observation with already frozen red-aware
remaining goal rates and a subsequently available regulation result.
Never used for live forecasts or automatic promotion. One row per fixture.
"""
import math

WEIGHTS=(0.,.125,.25,.5)
MIN_TRAIN=100
MIN_TEST=50


def finite(x,lo,hi):
    return type(x) in (int,float) and math.isfinite(x) and lo<=x<=hi


def valid(r):
    keys={"fixture_id","decision","result_available","minute","score","reds",
          "xg","base_remaining","final"}
    if type(r) is not dict or set(r)!=keys:
        raise ValueError("ROW_SCHEMA")
    if type(r["fixture_id"]) is not str or not r["fixture_id"] or len(r["fixture_id"])>128:
        raise ValueError("FIXTURE_ID")
    if any(type(r[k]) is not int for k in ("decision","result_available","minute")) or not 0<r["decision"]<r["result_available"] or not 15<=r["minute"]<=80:
        raise ValueError("ROW_CLOCK")
    for k in ("score","reds","final","xg","base_remaining"):
        if type(r[k]) is not list or len(r[k])!=2:
            raise ValueError("PAIR_SCHEMA")
    for k,maxval in (("score",10),("final",10),("reds",3)):
        if any(type(v) is not int or not 0<=v<=maxval for v in r[k]):
            raise ValueError("PAIR_VALUE")
    if any(a>b for a,b in zip(r["score"],r["final"])) or any(not finite(v,0,30) for v in r["xg"]) or any(not finite(v,.001,24) for v in r["base_remaining"]):
        raise ValueError("BAD_XG_RATE_OR_RESULT")


def rates(r,w):
    # Bounded relative pace residual; not a causal red-card estimate.
    # Cumulative xG may include pre-card play, hence candidate only.
    if w not in WEIGHTS:
        raise ValueError("WEIGHT")
    remaining=90-r["minute"]
    values=[]
    for baseline,xg in zip(r["base_remaining"],r["xg"]):
        pace=xg*remaining/r["minute"]
        ratio=max(.5,min(2.,(pace+.15)/(baseline+.15)))
        values.append(baseline*ratio**w)
    return values


def loss(r,w):
    return sum(mu-y*math.log(mu)+math.lgamma(y+1)
               for mu,y in zip(rates(r,w),[f-s for f,s in zip(r["final"],r["score"])]))


def evaluate(rows,*,split,assessment_end):
    out=dict(status="HOLD",production_recommendations="DISABLED",
             source_authenticated=False,model_calibrated=False,
             verified_forward_sample_credit=0,automatic_promotion=False)
    if type(split) is not int or type(assessment_end) is not int or not 0<split<assessment_end or type(rows) is not list or len(rows)>100000:
        raise ValueError("BAD_COHORT")
    seen=set()
    for r in rows:
        valid(r)
        if r["fixture_id"] in seen:
            raise ValueError("DUPLICATE_FIXTURE")
        seen.add(r["fixture_id"])
        if r["result_available"]>=assessment_end:
            raise ValueError("RESULT_NOT_AVAILABLE")
    train=[r for r in rows if r["decision"]<split and r["result_available"]<split]
    test=[r for r in rows if split<=r["decision"]<assessment_end]
    excluded=len(rows)-len(train)-len(test)
    out.update(train_n=len(train),test_n=len(test),excluded_cross_split_n=excluded,
               selected_weight=None,assessment=None)
    if len(train)<MIN_TRAIN or len(test)<MIN_TEST:
        return {**out,"reason":"INSUFFICIENT_CHRONOLOGICAL_COHORT"}
    def avg(rs,w):
        return math.fsum(loss(r,w) for r in rs)/len(rs)
    w=min(WEIGHTS,key=lambda k:(avg(train,k)+.01*k*k,k))
    base,candidate=avg(test,0.),avg(test,w)
    return {**out,"reason":"UNATTESTED_RESEARCH_ONLY","selected_weight":w,
            "assessment":{"baseline_poisson_nll":base,"candidate_poisson_nll":candidate,
                          "baseline_minus_candidate":base-candidate},
            "assessment_independently_unseen_verified":False}
