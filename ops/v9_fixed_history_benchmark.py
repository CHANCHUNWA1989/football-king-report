"""Fixed historical benchmark; no independent assessment or production promotion."""
import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path
from ops import v9_history_coverage as coverage

def load(root,manifest):
    audit=coverage.audit(root,manifest)
    if audit["quarantined_files"]!=0:
        raise ValueError("QUARANTINED_SCOPE")
    data={}
    for x in manifest["files"]:
        path=x["path"]
        raw=(Path(root)/path).read_bytes()
        if hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\x00"+raw).hexdigest()!=x["git_blob_sha"]:
            raise ValueError("BLOB_CHANGED_AFTER_AUDIT")
        season,league=path.split("/")
        rows=[]
        for r in json.loads(raw,object_pairs_hook=coverage.unique)["matches"]:
            s=r.get("score")
            if s=={} or (s is None and r.get("status")=="canceled"):continue
            s=s.get("ft") if isinstance(s,dict) else s
            rows.append((date.fromisoformat(r["date"]),r["team1"],r["team2"],*s))
        data[int(season[:4]),league]=sorted(rows)
    if sum(map(len,data.values()))!=audit["domestic_finished"]:raise ValueError("ROW_COUNT_CHANGED")
    return data

def poisson(rate):
    p=[math.exp(-rate)]
    for n in range(1,26):p.append(p[-1]*rate/n)
    return p

def probs(h,a):
    p,q=poisson(h),poisson(a)
    home=draw=away=0.0
    for i,x in enumerate(p):
        for j,y in enumerate(q):
            if i>j:home+=x*y
            elif i==j:draw+=x*y
            else:away+=x*y
    total=home+draw+away
    return tuple(v/total for v in (home,draw,away))

def add(teams,h,a,x,y):
    for t,g,c in ((h,x,y),(a,y,x)):
        s=teams[t];s[0]+=1;s[1]+=g;s[2]+=c

def predict(train,test,*,include_rates=False):
    if len(train)<100 or not test or max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("CHRONOLOGY")
    lh=sum(r[3] for r in train)/len(train);la=sum(r[4] for r in train)/len(train)
    mu=(lh+la)/2
    if min(lh,la)<=0:raise ValueError("LEAGUE_RATE")
    previous=defaultdict(lambda:[0,0,0]);current=defaultdict(lambda:[0,0,0])
    for _,h,a,x,y in train:add(previous,h,a,x,y)
    def rate(table,h,a):
        def strength(t):
            n,g,c=table.get(t,(0,0,0))
            return (g+8*mu)/(n+8)/mu,(c+8*mu)/(n+8)/mu
        ah,dh=strength(h);aa,da=strength(a)
        return lh*ah*da,la*aa*dh
    def bound(v):return max(.05,min(8,v))
    days=defaultdict(list)
    for row in test:days[row[0]].append(row)
    out=[]
    for day in sorted(days):
        for _,h,a,x,y in days[day]:
            b=tuple(map(bound,rate(previous,h,a)))
            now=rate(current,h,a)
            c=tuple(bound(math.sqrt(v*w)) for v,w in zip(b,now))
            row=(day,h,a,0 if x>y else 1 if x==y else 2,probs(*b),probs(*c))
            out.append((*row,b,c) if include_rates else row)
        for _,h,a,x,y in days[day]:add(current,h,a,x,y)
    return out

def metrics(rows):
    n=len(rows)
    result={"n":n}
    for col,name in ((4,"baseline"),(5,"candidate")):
        hits=sum(max(range(3),key=lambda k:r[col][k])==r[3] for r in rows)
        result[name]={"correct":hits,"accuracy":hits/n if n else None,
          "log_loss":sum(-math.log(max(r[col][r[3]],1e-15)) for r in rows)/n if n else None,
          "brier":sum(sum((r[col][k]-(k==r[3]))**2 for k in range(3)) for r in rows)/n if n else None}
    return result

def build(data):
    pooled=[];recent=[];scopes=[];excluded=[]
    for (year,league),test in sorted(data.items()):
        train=data.get((year-1,league))
        if train is None or len(train)<100 or not test:
            excluded.append({"year":year,"league":league,"n":len(test)});continue
        rows=predict(train,test);pooled.extend(rows)
        if year==2025:recent.extend(rows)
        scopes.append({"year":year,"league":league,**metrics(rows)})
    selected=[r for r in recent if max(r[5])>=.5]
    return {"schema":"v9-fixed-history-benchmark-v1","history_finished":sum(map(len,data.values())),
      "rolling":metrics(pooled),"latest":metrics(recent),"latest_candidate_threshold_50":{**metrics(selected),"coverage":len(selected)/len(recent) if recent else None},
      "scopes":scopes,"excluded_initial_scopes":excluded,
      "baseline_definition":"previous-season smoothed team attack/defence independent Poisson; not V8 joint fit",
      "candidate_definition":"equal geometric blend with current-season strictly prior-day form, fixed neutral eight-game prior",
      "same_day_updates_after_all_forecasts":True,"previously_inspected_history":True,
      "independent_assessment_count":0,"verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}

def selftest():
    tr=[(date(2018,8,1),"A","B",2,1)]*100
    day=date(2019,8,1);nxt=date(2019,8,2)
    test=[(day,"A","B",1,0),(day,"B","A",0,2),(nxt,"A","B",2,1)]
    changed=[(day,"A","B",0,5),*test[1:]]
    a,b=predict(tr,test),predict(tr,changed)
    assert [r[4:] for r in a[:2]]==[r[4:] for r in b[:2]]
    assert a[2][5]!=b[2][5]
    assert all(abs(sum(p)-1)<1e-10 for r in a for p in r[4:])
    try:predict(tr,[(date(2018,8,1),"A","B",1,0)])
    except ValueError:pass
    else:raise AssertionError("LEAKAGE")
    return 4

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",required=True);p.add_argument("--manifest",required=True)
    a=p.parse_args();result=build(load(a.root,json.loads(Path(a.manifest).read_text())))
    print(json.dumps({"synthetic_checks":selftest(),**result},allow_nan=False,sort_keys=True))
