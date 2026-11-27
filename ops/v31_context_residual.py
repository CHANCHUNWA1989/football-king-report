"""V31 context residual: domestic score/form and date-only schedule proxies.
No tactical tracking, physical fatigue, lineup or xG evidence.
"""
import math
from collections import defaultdict
from itertools import product
from ops import v9_stacking_research as s,v9_schedule_venue as sv,v8_multiseason as v
from ops import v5_ensemble_competition as e
from ops.v9_league_weights import ci

GRID=tuple(product((0.,.10,.20),(0.,.10,.20),(0.,.10,.20),(-.10,0.,.10)))
def features(rows):
    base=sv.features(rows);days=defaultdict(list);teams=defaultdict(list);out={}
    for r in rows:days[r[0]].append(r)
    for day,batch in sorted(days.items()):
        for _,h,a,x,y in sorted(batch):
            k=(day.isoformat(),h,a);z=base[k]
            if z is None or min(len(teams[h]),len(teams[a]))<5:out[k]=None;continue
            # Recent scoring/conceding is a score-based proxy, not tactical event data.
            def form(t):
                q=teams[t][-8:];return sum(x+y for x,y in q)/(len(q)+5)
            out[k]=(*z,sv.clamp((form(h)+form(a)-3.)/3.,-1.,1.))
        for _,h,a,x,y in sorted(batch):
            teams[h].append((x,y));teams[a].append((y,x))
    return out
def adjust(r,p):
    if p not in GRID:raise ValueError("CONTEXT_GRID")
    a=e.vec(r["stack"]);f=r["context"]
    if f is None or not any(p):return a
    if len(f)!=4 or any(not math.isfinite(x) or abs(x)>1 for x in f):raise ValueError("CONTEXT_FEATURE")
    d=sv.clamp(sum(x*y for x,y in zip(f[:3],p[:3])),-.4,.4)
    q=[a[0]*math.exp(d),a[1]*math.exp(f[3]*p[3]),a[2]*math.exp(-d)]
    return e.vec([x/math.fsum(q) for x in q])
def select(rows,anchor=(0.,0.,0.,0.)):
    if len(rows)<100 or any(r["season"]!=s.CAL or not "2024-07-01"<=r["date"]<"2025-07-01" for r in rows) or {r["y"] for r in rows}!={0,1,2}:raise ValueError("CONTEXT_CAL_SCOPE")
    def objective(p):
        penalty=.04*sum((a-b)**2 for a,b in zip(p,anchor))
        return (math.fsum(e.loss(adjust(r,p),r["y"]) for r in rows)/len(rows)+penalty,penalty,p)
    return min(GRID,key=objective)
def report(data,rows,totals):
    parts=s.partition(rows);model=s.fit_stack(parts["train"])
    def probs(a):return [e.vec([float(x) for x in p]) for p in model.predict_proba([s.features(r) for r in a])]
    t,w=s.select_calibration(parts["cal"],probs(parts["cal"]))
    cache={(season,league):features(data[season,league]) for season in (s.CAL,s.TEST) for league in v.LEAGUES}
    def attach(a):
        return [{**r,"context":cache[r["season"],r["league"]][e.key(r)],"stack":s.combine(p,r["candidate"],t,w)} for r,p in zip(a,probs(a))]
    cal=attach(parts["cal"]);test=attach(parts["test"])
    early=[r for r in cal if r["date"]<"2025-01-01"];late=[r for r in cal if r["date"]>="2025-01-01"]
    pooled=select(early);local={}
    for league in v.LEAGUES:
        a=[r for r in late if r["league"]==league]
        local[league]=select(a,pooled) if len(a)>=100 and {r["y"] for r in a}=={0,1,2} else pooled
    def choose(r):
        a=adjust(r,pooled);b=adjust(r,local[r["league"]])
        return e.vec([(x+y)/2 for x,y in zip(a,b)])
    scored=[{**r,"hybrid":r["stack"],"candidate":choose(r),"pooled_context":adjust(r,pooled)} for r in test]
    def evaluate(a,total):
        if not a or len(a)>total:raise ValueError("CONTEXT_SCOPE")
        m={k:e.metrics(a,lambda r:r[k]) for k in ("stack","pooled_context","candidate")}
        interval=ci(a)
        return {"n":len(a),"all_finished":total,"feature_available_n":sum(r["context"] is not None for r in a),"metrics":m,
            "paired_week_ci_stack_minus_context":interval,"historical_proper_score_gate":bool(interval and interval[0]>0 and all(m["candidate"][k]<m["stack"][k] for k in ("log_loss","brier")))}
    return {"schema":"v31-context-residual-research-v1","grid_size":len(GRID),"early_calibration_n":len(early),"late_calibration_n":len(late),
        "assessment_n":len(test),"pooled_coefficients":list(pooled),"league_coefficients":{k:list(a) for k,a in local.items()},
        "pooled":evaluate(scored,sum(totals.values())),"per_league":{k:evaluate([r for r in scored if r["league"]==k],totals[k]) for k in v.LEAGUES},
        "score_and_domestic_date_proxies_only":True,"calibration_reused_for_anchor":True,"assessment_previously_inspected":True,
        "actual_tactics_available":False,"physical_fatigue_available":False,"actual_xg_used":False,"prospective_validation":False,
        "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
