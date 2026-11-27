"""V8.0 integrated historical coverage and expanding-time research.
No odds, native cross-provider identity, or authenticated prospective credit.
"""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from ops import v5_joint_poisson as joint
from ops import v5_ensemble_competition as e
from ops.v6_forward_bundle import decode

LEAGUES=("de.1","en.1","es.1","fr.1","it.1","nl.1","pt.1")
SEASONS=tuple(f"{y}-{str(y+1)[-2:]}" for y in range(2021,2026))
PIN="e6744429ee395bc86f247348c6184bb08d4eb361"
def git_blob(raw):return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def parse(raw,season):
    doc=decode(raw)
    if not isinstance(doc,dict) or not isinstance(doc.get("matches"),list) or not 1<=len(doc["matches"])<=650:raise ValueError("BAD_ARCHIVE")
    seen=set();pairs=set();rows=[];missing=0
    start=date(int(season[:4]),7,1);end=date(start.year+1,7,1)
    for r in doc["matches"]:
        if not isinstance(r,dict):raise ValueError("BAD_ROW")
        h,a=r.get("team1"),r.get("team2")
        if not all(isinstance(v,str) and 0<len(v.strip())<=109 for v in (h,a)) or h==a:raise ValueError("BAD_TEAM")
        d=date.fromisoformat(r["date"])
        if not start<=d<end:raise ValueError("OUTSIDE_SEASON")
        k=(d,h,a)
        if k in seen or (h,a) in pairs:raise ValueError("DUPLICATE_FIXTURE")
        seen.add(k);pairs.add((h,a))
        s=r.get("score")
        if s=={} or (s is None and r.get("status")=="canceled"):
            missing+=1;continue
        s=s.get("ft") if isinstance(s,dict) else s
        if not isinstance(s,list) or len(s)!=2 or any(type(v) is not int or not 0<=v<=20 for v in s):raise ValueError("BAD_SCORE")
        rows.append((d,h,a,*s))
    return sorted(rows),missing,len(seen)

def load(root,manifest):
    expected={f"{s}/{l}.json" for s in SEASONS for l in LEAGUES}
    items=manifest.get("files",[])
    if manifest.get("commit")!=PIN or manifest.get("repository")!="openfootball/football.json" or len(items)!=len(expected) or {x["path"] for x in items}!=expected:raise ValueError("MANIFEST_SCOPE")
    data={};audit=[]
    for x in items:
        path=x["path"];f=Path(root)/path
        if not 0<f.stat().st_size<=500000 or f.stat().st_size!=x["bytes"]:raise ValueError("SOURCE_SIZE")
        raw=f.read_bytes()
        if git_blob(raw)!=x["git_blob_sha"]:raise ValueError("SOURCE_BLOB")
        season,l=path.split("/");league=l[:-5]
        try:
            rows,missing,total=parse(raw,season)
        except (ValueError,KeyError,TypeError) as exc:
            audit.append({"season":season,"league":league,"status":"QUARANTINE","reason":str(exc),"finished":0,"missing":None,"sha256":hashlib.sha256(raw).hexdigest()})
            continue
        data[season,league]=rows
        audit.append({"season":season,"league":league,"status":"PARTIAL" if missing else "PARSED","finished":len(rows),"missing":missing,"scheduled":total,"sha256":hashlib.sha256(raw).hexdigest()})
    return data,audit

def rolling_rates(base,teams,h,a,lh,la):
    # Role-independent current form, neutral prior 8 games. No unseen-team exclusion.
    league_mean=(lh+la)/2
    def strength(t):
        matches=teams.get(t,[])
        n=len(matches)
        return ((sum(x for x,y in matches)+8*league_mean)/(n+8)/league_mean,
                (sum(y for x,y in matches)+8*league_mean)/(n+8)/league_mean)
    ah,dh=strength(h);aa,da=strength(a)
    current=(lh*ah*da,la*aa*dh)
    return tuple(max(.05,min(8,math.sqrt(x*y))) for x,y in zip(base,current))

def replay(train,test,league,season):
    if len(train)<100 or not test or max(r[0] for r in train)>=min(r[0] for r in test):raise ValueError("BAD_TRAIN_ORDER")
    model=joint.fit(train,min(r[0] for r in test))
    lh=max(.05,sum(r[3] for r in train)/len(train));la=max(.05,sum(r[4] for r in train)/len(train))
    days=defaultdict(list);teams=defaultdict(list);out=[]
    for r in test:days[r[0]].append(r)
    for day in sorted(days):
        for _,h,a,x,y in days[day]:
            base=joint.rates(model,h,a)
            known=base is not None and all(.05<=v<=8 for v in base)
            if not known:base=(lh,la)
            p=e.vec(joint.probability(base))
            c=e.dc(*rolling_rates(base,teams,h,a,lh,la))
            out.append({"league":league,"season":season,"date":day.isoformat(),"home":h,"away":a,"y":0 if x>y else 1 if x==y else 2,"baseline":p,"candidate":c,"known_prior_team_pair":known})
        for _,h,a,x,y in days[day]:
            teams[h].append((x,y));teams[a].append((y,x))
    return out

def metrics(rows):
    return {"n":len(rows),"old_known_pair_count":sum(r["known_prior_team_pair"] for r in rows),
            "baseline":e.metrics(rows,lambda r:r["baseline"]),"candidate":e.metrics(rows,lambda r:r["candidate"])}

def build(data,audit):
    out=[];scopes=[];missing_scopes=[]
    for league in LEAGUES:
        for old,new in zip(SEASONS,SEASONS[1:]):
            tr=data.get((old,league));te=data.get((new,league))
            if tr is None or te is None or len(tr)<100 or not te:
                missing_scopes.append({"league":league,"season":new});continue
            cases=replay(tr,te,league,new);out+=cases
            scopes.append({"league":league,"season":new,**metrics(cases)})
    last=[r for r in out if r["season"]=="2025-26"]
    selected=[r for r in last if max(r["candidate"])>=.50]
    return {"schema":"v8-multiseason-research-v1","source_commit":PIN,"historical_finished":sum(x["finished"] for x in audit),
        "source_files":audit,"missing_scopes":missing_scopes,"league_season_metrics":scopes,
        "rolling_all":metrics(out),"latest_season_assessment":metrics(last),
        "latest_season_fixed_threshold_50":{**metrics(selected),"coverage":len(selected)/len(last) if last else None},
        "baseline_definition":"prior-season joint Poisson with neutral fallback, not full V6.4 ensemble",
        "candidate_definition":"fixed prior/current geometric blend plus Dixon-Coles",
        "assessment_some_previously_inspected":True,"result_source_independently_verified":False,
        "market_comparison_available":False,"prospective_validation":False,"production_recommendations":"DISABLED","automatic_promotion":False,"status":"HOLD"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--manifest",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    data,audit=load(a.input_dir,decode(Path(a.manifest).read_bytes()))
    out=build(data,audit)
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in out.items() if k not in ("source_files","league_season_metrics")},allow_nan=False))
if __name__=="__main__":main()
