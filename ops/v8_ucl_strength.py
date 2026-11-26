"""V8.2 UCL-only group/league-phase country and club strength challenger.
Historical reconstructed date-only research, not a live input or promotion.
"""
import argparse
from collections import defaultdict
from datetime import date
import hashlib,json,math,re
from pathlib import Path
from ops.v8_multiseason import git_blob,PIN
from ops.v6_forward_bundle import decode
from ops import v5_joint_poisson as j,v5_ensemble_competition as e
SEASONS=tuple(f"{y}-{str(y+1)[-2:]}" for y in range(2011,2020))+("2024-25",)
GROUP=re.compile(r"Group [A-H]")
LEAGUE=re.compile(r"League, Matchday [1-8]")
TEAM=re.compile(r".+ \(([A-Z]{3})\)")
def parse(raw,season):
    doc=decode(raw);rows=[];seen=set();excluded=0
    start=date(int(season[:4]),7,1);end=date(start.year+1,7,1)
    for r in doc["matches"]:
        phase=LEAGUE if season=="2024-25" else GROUP
        if not phase.fullmatch(r["round"]):excluded+=1;continue
        d=date.fromisoformat(r["date"]);h,a=r["team1"],r["team2"]
        mh,ma=TEAM.fullmatch(h),TEAM.fullmatch(a)
        if not mh or not ma or h==a or not start<=d<end or (d,h,a) in seen:raise ValueError("INVALID_FIXTURE")
        seen.add((d,h,a));s=r["score"]
        ft=s.get("ft") if isinstance(s,dict) else None
        if not isinstance(ft,list) or len(ft)!=2 or any(type(x) is not int or not 0<=x<=20 for x in ft):raise ValueError("INVALID_REGULATION_SCORE")
        rows.append((d,h,a,mh[1],ma[1],*ft,season))
    if len(rows)!=(144 if season=="2024-25" else 96):raise ValueError("INCOMPLETE_PHASE")
    return sorted(rows),excluded
def load(root,m):
    expected={s+"/uefa.cl.json" for s in SEASONS}
    if m["commit"]!=PIN or m["repository"]!="openfootball/football.json" or len(m["files"])!=10 or {x["path"] for x in m["files"]}!=expected:raise ValueError("MANIFEST")
    rows=[];receipts=[]
    for x in m["files"]:
        f=Path(root)/x["path"]
        if not 0<f.stat().st_size==x["bytes"]<=500000:raise ValueError("SIZE")
        raw=f.read_bytes()
        if git_blob(raw)!=x["git_blob_sha"]:raise ValueError("BLOB")
        r,n=parse(raw,x["path"].split("/")[0]);rows+=r
        receipts.append({"path":x["path"],"sha256":hashlib.sha256(raw).hexdigest(),"included":len(r),"excluded_knockout":n})
    return sorted(rows),receipts
def rates(history,day,h,a,ch,ca):
    if any(r[0]>=day for r in history):raise ValueError("FUTURE_HISTORY")
    # A 365-day half-life with explicit shrinkage makes long archive gaps
    # revert toward neutral. Club labels are exact, never fuzzy-matched.
    totals=[0.,0.,0.]
    clubs=defaultdict(lambda:[0.,0.,0.]);countries=defaultdict(lambda:[0.,0.,0.])
    for d,x,y,cx,cy,gf,ga,_ in history:
        w=2**(-(day-d).days/365)
        totals[0]+=w;totals[1]+=w*gf;totals[2]+=w*ga
        for t,c,f,g in ((x,cx,gf,ga),(y,cy,ga,gf)):
            for bucket in (clubs[t],countries[c]):
                bucket[0]+=w;bucket[1]+=w*f;bucket[2]+=w*g
    # Fixed weak neutral prior; baseline uses exactly the same earlier matches.
    lh=(totals[1]+20*1.5)/(totals[0]+20);la=(totals[2]+20*1.2)/(totals[0]+20)
    mu=(lh+la)/2
    def strength(t,c):
        n,f,g=countries[c];cf=(f+20*mu)/(n+20);cg=(g+20*mu)/(n+20)
        n,f,g=clubs[t]
        return (f+8*cf)/(n+8)/mu,(g+8*cg)/(n+8)/mu
    ah,dh=strength(h,ch);aa,da=strength(a,ca)
    updated=(lh*ah*da,la*aa*dh)
    return (lh,la),tuple(max(.05,min(8,math.sqrt(b*v))) for b,v in zip((lh,la),updated))
def replay(rows):
    days=defaultdict(list);seen=set()
    for r in rows:
        k=r[:3]
        if k in seen:raise ValueError("DUPLICATE")
        seen.add(k);days[r[0]].append(r)
    prior=[];out=[]
    for day in sorted(days):
        for _,h,a,ch,ca,x,y,season in days[day]:
            if len(prior)<96:continue
            b,c=rates(prior,day,h,a,ch,ca)
            out.append({"date":day.isoformat(),"season":season,"y":0 if x>y else 1 if x==y else 2,"baseline":e.vec(j.probability(b)),"candidate":e.dc(*c)})
        prior+=days[day]
    return out
def metrics(rows):
    return {"n":len(rows),"baseline":e.metrics(rows,lambda r:r["baseline"]),"candidate":e.metrics(rows,lambda r:r["candidate"])}
def build(rows):
    a=replay(rows);last=[r for r in a if r["season"]=="2024-25"]
    selected=[r for r in last if max(r["candidate"])>=.5]
    return {"schema":"v8-2-ucl-country-club-research-v1","historical_phase_matches":len(rows),"all_assessment":metrics(a),
        "latest_league_phase":metrics(last),"latest_candidate_threshold_50":{**metrics(selected),"coverage":len(selected)/len(last) if last else None},
        "by_season":{s:metrics([r for r in a if r["season"]==s]) for s in SEASONS},
        "archive_gap_2020_21_to_2023_24":True,"exact_label_only":True,"no_domestic_league_conversion":True,
        "current_ucl_source_qualified":False,"current_fixture_forecasts":0,"prospective_validation":False,"independent_result_authentication":False,
        "verified_forward_sample_credit":0,"production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("input-dir","manifest","output"):p.add_argument("--"+k,required=True)
    a=p.parse_args();rows,receipts=load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=build(rows);out["source_receipts"]=receipts
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k not in ("by_season","source_receipts")},allow_nan=False))
if __name__=="__main__":main()
