"""Retrospective common 25x25 score PMFs, separate from the old 1X2 audit.

Fitted Poisson/DC use their actual upstream grid, not fixed rho stand-ins.
Rate-derived original A/dynamic grids omit and bound, not alias, the tail.
Date-only weights use earlier 1X2 outcomes with a two-day proxy embargo.
No trusted availability timestamps, tradable quotes, promotion or fresh OOS.
"""
from math import exp, fsum, isfinite, log
from ops.date_only_ensemble_replay import evaluate_date_fusion, MODELS
from ops.asian_handicap_research import grade, TYPES
from ops.real_2026_three_market_oos import total_grade, _score, CLASSES_1X2

SIZE = 25
AH = (-1.25,-1.5,-1.75,-2.)
OU = (2.5,2.75,3.)
LIMIT = 1e-7


def checked_grid(raw,size=SIZE):
    if len(raw)!=size or any(len(row)!=size for row in raw):
        raise ValueError("INVALID_COMMON_GRID_SHAPE")
    g=tuple(tuple(float(v) for v in row) for row in raw)
    if any(not isfinite(v) or not 0<=v<=1 for row in g for v in row):
        raise ValueError("INVALID_COMMON_GRID_PROBABILITY")
    mass=fsum(fsum(row) for row in g)
    if abs(mass-1)>1e-7:
        raise ValueError("INVALID_COMMON_GRID_MASS")
    return tuple(tuple(v/mass for v in row) for row in g)


def rates_grid(h,a):
    def pm(rate):
        if type(rate) not in (int,float) or not isfinite(rate) or not .08<=rate<=6.5:
            raise ValueError("INVALID_RATE")
        x=[exp(-rate)]
        for i in range(1,SIZE):
            x.append(x[-1]*rate/i)
        return x
    x,y=pm(h),pm(a)
    mass=fsum(x)*fsum(y)
    tail=max(0.,1-mass)
    if tail>LIMIT:
        raise ValueError("RATE_TAIL_EXCEEDS_LIMIT")
    return checked_grid([[v*w/mass for w in y] for v in x]),tail


def fitted_grid(model,h,a):
    small=checked_grid(model.predict(h,a,max_goals=SIZE,normalize=True).grid)
    wide=checked_grid(model.predict(h,a,max_goals=35,normalize=True).grid,35)
    retained=fsum(wide[i][j] for i in range(SIZE) for j in range(SIZE))
    tail=max(0.,1-retained)
    if tail>LIMIT or max(abs(small[i][j]-wide[i][j]/retained)
                         for i in range(SIZE) for j in range(SIZE))>LIMIT:
        raise ValueError("FITTED_GRID_SUPPORT_DRIFT")
    return small,tail


def projections(grid):
    margin=[0.]*(2*SIZE-1)
    total=[0.]*(2*SIZE-1)
    for i,row in enumerate(grid):
        for j,v in enumerate(row):
            margin[i-j+SIZE-1]+=v
            total[i+j]+=v
    p={"HOME":fsum(margin[SIZE:]),"DRAW":margin[SIZE-1],
       "AWAY":fsum(margin[:SIZE-1])}
    result={"1X2":p}
    for line in AH:
        d=dict.fromkeys(TYPES,0.)
        for k,v in enumerate(margin):
            m=k-(SIZE-1)
            d[grade(max(m,0),max(-m,0),"HOME",line)]+=v
        result["AH_HOME_"+str(line)]=d
    for line in OU:
        d=dict.fromkeys(TYPES,0.)
        for k,v in enumerate(total):
            d[total_grade(k,0,"OVER",line)]+=v
        result["OVER_"+str(line)]=d
    return result


def mix(grids,w):
    if set(grids)!=set(MODELS) or set(w)!=set(MODELS) or any(
            type(v) not in (int,float) or not isfinite(v) or not 0<=v<=1
            for v in w.values()) or abs(fsum(w.values())-1)>1e-10:
        raise ValueError("INVALID_COMMON_WEIGHTS")
    return checked_grid([[fsum(w[m]*grids[m][i][j] for m in MODELS)
                          for j in range(SIZE)] for i in range(SIZE)])


def evaluate(days,actual,grids):
    n=len(days)
    if not 1<=n<=5000 or len(actual)!=n or len(grids)!=n:
        raise ValueError("INVALID_COMMON_COHORT")
    clean=[]
    for row,score in zip(grids,actual):
        if set(row)!=set(MODELS) or len(score)!=2 or any(
                type(v) is not int or not 0<=v<SIZE for v in score):
            raise ValueError("INVALID_COMMON_CASE")
        clean.append({m:checked_grid(row[m]) for m in MODELS})
    vectors={m:[projections(g[m])["1X2"] for g in clean] for m in MODELS}
    outcomes=["HOME" if h>a else "DRAW" if h==a else "AWAY" for h,a in actual]
    weights=evaluate_date_fusion(days,vectors,outcomes)
    traces={row["row_index"]:row for row in weights["weight_trace"]}
    models=(*MODELS,"uniform","adaptive")
    scores={m:{} for m in models}
    active={m:{} for m in models}
    for i,(h,a) in enumerate(actual):
        w=traces[i]["weights"]
        row=clean[i]
        all_grids={**row,"uniform":mix(row,{m:.25 for m in MODELS}),
                   "adaptive":mix(row,w)}
        observed={"1X2":outcomes[i],**{"AH_HOME_"+str(line):grade(h,a,"HOME",line)
                   for line in AH},**{"OVER_"+str(line):total_grade(h,a,"OVER",line)
                   for line in OU}}
        for m,g in all_grids.items():
            values={k:_score(v,observed[k],CLASSES_1X2 if k=="1X2" else TYPES)
                    for k,v in projections(g).items()}
            prob=g[h][a]
            values["EXACT_SCORE"]=(fsum(v*v for row in g for v in row)-2*prob+1,
                                   -log(max(prob,1e-15)))
            for k,v in values.items():
                scores[m].setdefault(k,[]).append(v)
                if traces[i]["prior_count"]>=30:
                    active[m].setdefault(k,[]).append(v)
    def summarize(table):
        return {m:{k:{"n":len(v),"mean_brier":fsum(x[0] for x in v)/len(v),
                       "mean_logloss":fsum(x[1] for x in v)/len(v)}
                   for k,v in markets.items()} for m,markets in table.items()}
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "model_promoted":False,"positive_ev_verified":False,
            "certified_prospective_samples":0,"production_weights_changed":False,
            "date_only_proxy_not_actual_result_availability":True,
            "reused_historical_cohort":True,"fixed_hypothetical_lines":True,
            "paired_n":n,"adaptive_active_n":weights["adaptive_active_n"],
            "support":SIZE,"all_cohort":summarize(scores),
            "active_cohort":summarize(active) if weights["adaptive_active_n"] else None}
