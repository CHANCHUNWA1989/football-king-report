"""Descriptive five-grade calibration on already validated paired records.

Never fits or modifies probabilities. Different lines have different feasible
grades; keep exact line and model-version pair separate. No independent
authentication, no inferential confidence bounds, no release authorization.
"""
import math
from collections import defaultdict
from asian_handicap_research import TYPES, grade

MIN_CASES=100
MIN_WEEKS=8
MIN_BIN_CASES=20
BINS=10


def _bins(values):
    buckets=[[] for _ in range(BINS)]
    for p,y in values:
        buckets[min(BINS-1,int(p*BINS))].append((p,y))
    rows=[]
    covered=0
    weighted_error=0.0
    for i,b in enumerate(buckets):
        n=len(b)
        entry={"lower":i/BINS,"upper":(i+1)/BINS,"upper_inclusive":i==BINS-1,
               "n":n,"mean_forecast":None,"observed_fraction":None,"signed_gap":None}
        if n>=MIN_BIN_CASES:
            p=math.fsum(x for x,_ in b)/n
            y=math.fsum(v for _,v in b)/n
            entry.update(mean_forecast=p,observed_fraction=y,signed_gap=p-y)
            covered+=n
            weighted_error+=n*abs(p-y)
        rows.append(entry)
    # Never present error on a selectively covered subset as global ECE.
    return {"bins":rows,"covered_count":covered,
            "coverage_fraction":covered/len(values) if values else None,
            "ece":weighted_error/len(values) if values and covered==len(values) else None}


def _model(records,idx,feasible):
    by_grade={}
    for g in TYPES:
        if g not in feasible:
            by_grade[g]={"status":"STRUCTURALLY_IMPOSSIBLE_FOR_LINE"}
            continue
        v=[(r[0][4][idx][g],r[0][3]==g) for r in records]
        n=len(v)
        mean=math.fsum(p for p,_ in v)/n
        observed=math.fsum(y for _,y in v)/n
        by_grade[g]={"status":"DESCRIPTIVE_ONLY","mean_forecast":mean,
                     "observed_fraction":observed,"signed_gap":mean-observed,
                     "binary_brier":math.fsum((p-y)**2 for p,y in v)/n,
                     **_bins(v)}
    top=[]
    for r,_,_ in records:
        p=r[4][idx]
        # Stable grade-order tie breaking, identical for both models.
        g=max(TYPES,key=lambda g:p[g])
        top.append((p[g],r[3]==g))
    n=len(top)
    confidence=math.fsum(p for p,_ in top)/n
    accuracy=math.fsum(y for _,y in top)/n
    return {"by_grade":by_grade,"top_grade":{
        "mean_confidence":confidence,"observed_accuracy":accuracy,
        "signed_confidence_gap":confidence-accuracy,
        **_bins(top)}}


def diagnose(records):
    """Input contract: list of validated (parsed row, UTC week, model pair)."""
    groups=defaultdict(list)
    for rec in records:
        row,week,pair=rec
        # Do not pool leagues, exact lines or versions.
        groups[(row[1],row[2],pair)].append(rec)
    results=[]
    for (league,units,pair),items in sorted(groups.items()):
        weeks=len({r[1] for r in items})
        entry={"league_id":league,"handicap":units/4,
               "model_ids":{"baseline":pair[0],"challenger":pair[1]},
               "n":len(items),"utc_iso_week_count":weeks,"models":None,
               "status":"INSUFFICIENT_SAMPLE"}
        if len(items)>=MIN_CASES and weeks>=MIN_WEEKS:
            feasible={grade(max(0,m),max(0,-m),"HOME",units/4) for m in range(-25,26)}
            entry.update(status="DESCRIPTIVE_ONLY",
                         models={name:_model(items,idx,feasible)
                                 for idx,name in enumerate(("baseline","challenger"))})
        results.append(entry)
    return {"descriptive_only":True,"source_authenticated":False,
            "calibration_verified":False,"recalibration_applied":False,
            "confidence_interval_available":False,"min_cases":MIN_CASES,
            "min_weeks":MIN_WEEKS,"min_bin_cases":MIN_BIN_CASES,
            "groups":results}
