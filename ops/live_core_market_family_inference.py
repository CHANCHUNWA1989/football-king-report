"""Retrospective simultaneous interval sensitivity for the locked blend50.

The six non-redundant metric definitions are fixed for two seasons x three
leagues. Approximate Bonferroni percentile intervals, not independent trials.
"""
import math
import random

UNIQUE_METRICS=("1x2_log_loss","1x2_brier","under25_brier",
                "home_minus_075_grade_brier","over_225_grade_brier","over_300_grade_brier")
ALIASES={"home_minus_025_grade_brier":"1x2_brier",
         "home_plus_025_grade_brier":"1x2_brier",
         "under_275_grade_brier":"over_300_grade_brier"}
FAMILY_SIZE=36
DRAWS=20000
ALPHA=.05
MIN_WEEKS=12
MIN_ROWS=300 # descriptive eligibility only; no forward credit

def family_intervals(weekly, *, draws=DRAWS):
    if type(draws) is not int or draws<DRAWS:raise ValueError("BOOTSTRAP_RESOLUTION")
    if set(weekly)!=set(UNIQUE_METRICS)|set(ALIASES):raise ValueError("METRIC_SCOPE")
    keys=sorted(weekly[UNIQUE_METRICS[0]])
    counts=[]
    for key in keys:
        n=weekly[UNIQUE_METRICS[0]][key][1]
        if type(n) is not int or n<=0:raise ValueError("WEEK_COUNT")
        counts.append(n)
    for metric,groups in weekly.items():
        if set(groups)!=set(keys):raise ValueError("WEEK_ALIGNMENT")
        for key,n in zip(keys,counts):
            v,c=groups[key]
            if type(c) is not int or c!=n or type(v) not in (int,float) or not math.isfinite(v):
                raise ValueError("BAD_WEEK_BLOCK")
    for alias,target in ALIASES.items():
        if any(not math.isclose(weekly[alias][k][0],weekly[target][k][0],rel_tol=0,abs_tol=1e-10) for k in keys):
            raise ValueError("EQUIVALENT_MARKET_MISMATCH")
    n=sum(counts)
    tail=ALPHA/(2*FAMILY_SIZE)
    # Keep results explicitly unavailable for insufficient coverage.
    adequate=len(keys)>=MIN_WEEKS and n>=MIN_ROWS
    intervals={m:None for m in UNIQUE_METRICS}
    if adequate:
        rng=random.Random(20261126)
        vectors=[[weekly[m][k][0] for k in keys] for m in UNIQUE_METRICS]
        samples=[[] for _ in UNIQUE_METRICS]
        for _ in range(draws):
            chosen=[rng.randrange(len(keys)) for _ in keys]
            total=sum(counts[i] for i in chosen)
            for v,out in zip(vectors,samples):
                out.append(math.fsum(v[i] for i in chosen)/total)
        lo=max(0,math.floor(tail*draws)-1)
        hi=min(draws-1,math.ceil((1-tail)*draws))
        for m,s in zip(UNIQUE_METRICS,samples):
            s.sort();intervals[m]=[s[lo],s[hi]]
    return {"family_size":FAMILY_SIZE,"family_alpha":ALPHA,"individual_nominal_confidence":1-ALPHA/FAMILY_SIZE,
            "draws":draws if adequate else 0,"week_blocks":len(keys),"n":n,
            "descriptive_coverage_eligible":adequate,"intervals":intervals,
            "aliases_not_independent_metrics":dict(ALIASES),
            "positive_lower_bound_metrics":[m for m,v in intervals.items() if v is not None and v[0]>0],
            "negative_upper_bound_metrics":[m for m,v in intervals.items() if v is not None and v[1]<0],
            "approximate_cluster_bootstrap":True,"preregistered_independent_trial":False,
            "qualification_credit":0,"production_recommendations":"DISABLED"}
