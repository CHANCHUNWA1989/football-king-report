"""V8.3 UCL opponent-adjusted hierarchical Elo challenger. Fixed weights, research only."""
import argparse
from collections import defaultdict
from datetime import date
import json,math,random
from pathlib import Path
from ops import v8_ucl_strength as u
from ops import v5_joint_poisson as j,v5_ensemble_competition as e
from ops.v6_forward_bundle import decode

HALF_LIFE=365
HOME_ELO=55.
K_CLUB=20.
K_COUNTRY=4.
def decayed(value,day):
    r,stamp=value
    if stamp>day:raise ValueError("FUTURE_RATING")
    return r*2**(-(day-stamp).days/HALF_LIFE)
def rating(state,key,day):
    return decayed(state.get(key,(0.,day)),day)
def difference(clubs,countries,h,a,ch,ca,day):
    return rating(clubs,h,day)-rating(clubs,a,day)+rating(countries,ch,day)-rating(countries,ca,day)
def opponent_rates(base,diff):
    if not math.isfinite(diff) or any(not math.isfinite(v) or not .05<=v<=8 for v in base):raise ValueError("BAD_RATE")
    # Base rates already include home advantage; no duplicate home adjustment.
    factor=10**(max(-400.,min(400.,diff))/1600)
    return max(.05,min(8,base[0]*factor)),max(.05,min(8,base[1]/factor))
def update(clubs,countries,rows,day):
    cd=defaultdict(float);nd=defaultdict(float)
    for d,h,a,ch,ca,x,y,_ in rows:
        if d!=day:raise ValueError("WRONG_UPDATE_DAY")
        diff=difference(clubs,countries,h,a,ch,ca,day)
        expected=1/(1+10**(-(diff+HOME_ELO)/400))
        delta=(1 if x>y else .5 if x==y else 0)-expected
        cd[h]+=K_CLUB*delta;cd[a]-=K_CLUB*delta
        nd[ch]+=K_COUNTRY*delta;nd[ca]-=K_COUNTRY*delta
    # All games use the same pre-day ratings.
    for state,changes in ((clubs,cd),(countries,nd)):
        for key,v in changes.items():state[key]=(rating(state,key,day)+v,day)
def replay(rows):
    days=defaultdict(list);seen=set()
    for r in rows:
        if r[:3] in seen:raise ValueError("DUPLICATE")
        seen.add(r[:3]);days[r[0]].append(r)
    prior=[];out=[];clubs={};countries={}
    for day in sorted(days):
        for _,h,a,ch,ca,x,y,season in days[day]:
            if len(prior)<96:continue
            b,c=u.rates(prior,day,h,a,ch,ca)
            diff=difference(clubs,countries,h,a,ch,ca,day)
            p=e.dc(*c);q=e.dc(*opponent_rates(b,diff))
            out.append({"date":day.isoformat(),"season":season,"home":h,"away":a,"y":0 if x>y else 1 if x==y else 2,
                "baseline":p,"elo":q,"hybrid":e.vec([(v+w)/2 for v,w in zip(p,q)])})
        update(clubs,countries,days[day],day)
        prior+=days[day]
    return out
MODELS=("baseline","elo","hybrid")
def metrics(rows):return {k:e.metrics(rows,lambda r:r[k]) for k in MODELS}
def ci(rows):
    groups=defaultdict(list)
    for r in rows:
        groups[date.fromisoformat(r["date"]).strftime("%G-W%V")].append(e.loss(r["baseline"],r["y"])-e.loss(r["hybrid"],r["y"]))
    if len(groups)<12:return None
    blocks=list(groups.values());rng=random.Random(20261126);a=[]
    for _ in range(1000):
        values=[v for b in rng.choices(blocks,k=len(blocks)) for v in b];a.append(sum(values)/len(values))
    a.sort();return [a[25],a[974]]
def build(rows):
    out=replay(rows);last=[r for r in out if r["season"]=="2024-25"]
    if not last:raise ValueError("NO_LATEST_COHORT")
    m=metrics(last);interval=ci(last)
    common=[r for r in last if max(r["baseline"])>=.5]
    return {"schema":"v8-3-ucl-opponent-adjusted-research-v1","all_assessment":metrics(out),"latest_league_phase":m,
        "same_baseline_selected":{"n":len(common),"coverage":len(common)/len(last),"metrics":metrics(common)},
        "individual_threshold_50":{k:{"n":len(a),"coverage":len(a)/len(last),"metrics":e.metrics(a,lambda r:r[k])} for k in MODELS for a in [[r for r in last if max(r[k])>=.5]]},
        "paired_week_ci_baseline_minus_hybrid":interval,"historical_gate":bool(interval and interval[0]>0 and m["hybrid"]["log_loss"]<m["baseline"]["log_loss"] and m["hybrid"]["brier"]<m["baseline"]["brier"]),
        "archive_gap_2020_21_to_2023_24":True,"assessment_previously_inspected":True,"current_fixture_forecasts":0,
        "prospective_validation":False,"market_comparison_available":False,"verified_forward_sample_credit":0,
        "production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();rows,_=u.load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=build(rows)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
