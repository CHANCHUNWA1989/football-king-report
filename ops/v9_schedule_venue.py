"""V9.4 domestic schedule/venue proxy challenger. Dates only; not physical fatigue."""
import argparse,json,math,random
from collections import defaultdict
from datetime import date
from itertools import product
from pathlib import Path
from ops import v8_multiseason as v, v5_ensemble_competition as e
from ops.v6_forward_bundle import decode

DEV=("2022-23","2023-24","2024-25")
TEST="2025-26"
GRID=tuple(product((0.,.10,.20),(0.,.10,.20),(0.,.10,.20)))
def clamp(x,lo,hi):return max(lo,min(hi,x))
def features(rows):
    days=defaultdict(list);seen=set();history=defaultdict(list);venue=defaultdict(list);out={}
    for r in rows:
        d,h,a,x,y=r
        if (d,h,a) in seen or h==a:raise ValueError("INVALID_FIXTURE")
        seen.add((d,h,a));days[d].append(r)
    for d in sorted(days):
        for _,h,a,x,y in sorted(days[d]):
            hh,ah=history[h],history[a]
            def rest(hist):return min(14,(d-hist[-1]).days) if hist else None
            rh,ra=rest(hh),rest(ah)
            def count(hist):return sum(0<(d-t).days<=14 for t in hist)
            def venue_form(t,role):
                z=venue[t,role][-8:]
                return sum(gf-ga for gf,ga in z)/(len(z)+5)
            if rh is not None and ra is not None:
                out[d.isoformat(),h,a]=(clamp((rh-ra)/7,-1,1),clamp((count(ah)-count(hh))/3,-1,1),clamp((venue_form(h,"H")-venue_form(a,"A"))/2,-1,1))
            else:out[d.isoformat(),h,a]=None
        for _,h,a,x,y in sorted(days[d]):
            history[h].append(d);history[a].append(d)
            venue[h,"H"].append((x,y));venue[a,"A"].append((y,x))
    return out
def adjust(p,f,params):
    p=e.vec(p)
    if params not in GRID:raise ValueError("PARAMETERS")
    if f is None:return p
    if len(f)!=3 or any(not math.isfinite(x) or not -1<=x<=1 for x in f):raise ValueError("FEATURE")
    shift=clamp(sum(a*b for a,b in zip(f,params)),-.4,.4)
    z=[p[0]*math.exp(shift),p[1],p[2]*math.exp(-shift)]
    return e.vec([x/sum(z) for x in z])
def fit(rows):
    if len(rows)<500 or any(r["season"] not in DEV or r["date"]>="2025-07-01" for r in rows):raise ValueError("DEVELOPMENT")
    def objective(par):
        penalty=.02*sum(x*x for x in par)
        return (sum(e.loss(adjust(r["candidate"],r["features"],par),r["y"]) for r in rows)/len(rows)+penalty,penalty,par)
    return min(GRID,key=objective)
def ci(rows,par):
    groups=defaultdict(list)
    for r in rows:
        groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(e.loss(r["candidate"],r["y"])-e.loss(adjust(r["candidate"],r["features"],par),r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261126);values=[]
    for _ in range(1000):
        z=[x for b in rng.choices(blocks,k=len(blocks)) for x in b];values.append(sum(z)/len(z))
    values.sort();return [values[25],values[974]]
def evaluate(data):
    rows=[]
    for league in v.LEAGUES:
        for old,new in zip(v.SEASONS,v.SEASONS[1:]):
            tr,te=data[old,league],data[new,league]
            f=features(te)
            cases=v.replay(tr,te,league,new)
            if len(cases)!=len(f):raise ValueError("COHORT")
            rows += [{**r,"features":f[e.key(r)]} for r in cases]
    dev=[r for r in rows if r["season"] in DEV];test=[r for r in rows if r["season"]==TEST]
    if not test or any(r["date"]<"2025-07-01" for r in test):raise ValueError("ASSESSMENT")
    params=fit(dev)
    b=lambda r:r["candidate"]
    c=lambda r:adjust(b(r),r["features"],params)
    def scores(a):return {"baseline":e.metrics(a,b),"candidate":e.metrics(a,c)}
    known=[r for r in test if r["features"] is not None]
    m=scores(test);interval=ci(test,params)
    return {"schema":"v9-4-domestic-schedule-venue-research-v1","development_n":len(dev),"assessment_n":len(test),
        "feature_available_n":len(known),"feature_coverage":len(known)/len(test),"selected_coefficients":dict(zip(("rest","congestion","venue_form"),params)),
        "grid_size":len(GRID),"same_fixture":m,"known_feature_same_fixture":scores(known),
        "per_league":{k:scores([r for r in test if r["league"]==k]) for k in v.LEAGUES},
        "paired_week_ci_baseline_minus_candidate":interval,
        "historical_proper_score_gate":bool(interval and interval[0]>0 and m["candidate"]["log_loss"]<m["baseline"]["log_loss"] and m["candidate"]["brier"]<m["baseline"]["brier"]),
        "baseline_definition":"V8 domestic dynamic DC; not full seven-model hybrid",
        "league_only_date_proxy_not_full_schedule_or_physiology":True,"missing_features_use_baseline":True,
        "assessment_previously_inspected":True,"prospective_validation":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();data,_=v.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=evaluate(data)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
