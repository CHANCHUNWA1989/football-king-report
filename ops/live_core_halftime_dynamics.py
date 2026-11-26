"""Frozen historical halftime score-state study, not a live prediction engine."""
import json
import math
from collections import Counter,defaultdict
from urllib.request import Request,build_opener
from live_core_multi_source import blob,checked,row,unique,NoRedirect,LIMIT
from vnext_direct_transport_offline import unique_object,reject_constant
from live_core_low_score_calibration import PINS

COVERAGE={"2020-21":350,"2021-22":358}
SHRINK=50


def parse(raw,season):
    if blob(raw)!=PINS[season]:raise ValueError("PIN_CHANGED")
    d=json.loads(checked(raw),object_pairs_hook=unique_object,parse_constant=reject_constant)
    if d["name"]!="English Premier League "+season.replace("-","/") or len(d["matches"])!=380:
        raise ValueError("SCOPE")
    keys=[];out=[]
    start=int(season[:4])
    for m in d["matches"]:
        day,h,a,x,y=row(m["date"],m["team1"],m["team2"],m["score"]["ft"])
        keys.append((day,h,a,x,y))
        if not f"{start}-07-01"<=day<f"{start+1}-07-01":raise ValueError("DATE")
        ht=m["score"].get("ht")
        if ht is None:continue
        _,_,_,i,j=row(day,h,a,ht)
        if i>x or j>y:raise ValueError("HALFTIME_SCORE")
        out.append((day,h,a,i,j,x,y))
    unique(keys)
    if len(out)!=COVERAGE[season]:raise ValueError("COVERAGE")
    return sorted(out)


def fetch(season):
    url=f"https://raw.githubusercontent.com/openfootball/football.json/master/{season}/en.1.json"
    with build_opener(NoRedirect()).open(Request(url,headers={"User-Agent":"FootballKingResearch/1.0","Accept":"application/json"}),timeout=15) as res:
        if res.geturl()!=url or res.status!=200:raise ValueError("HTTP_SOURCE")
        raw=res.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError("SIZE")
    return parse(raw,season)


def bucket(h,a):return max(-2,min(2,h-a))


def fit(rows):
    if not rows:raise ValueError("EMPTY_TRAIN")
    pooled=Counter();groups=defaultdict(Counter)
    for _,_,_,h,a,x,y in rows:
        if any(type(v) is not int or v<0 for v in (h,a,x,y)) or h>x or a>y:
            raise ValueError("SCORE")
        k=(x-h,y-a)
        pooled[k]+=1;groups[bucket(h,a)][k]+=1
    return pooled,dict(groups)


def distribution(model,h,a,conditional):
    if any(type(v) is not int or v<0 for v in (h,a)) or type(conditional) is not bool:
        raise ValueError("STATE")
    pooled,groups=model
    n=sum(pooled.values())
    g=groups.get(bucket(h,a),Counter());ng=sum(g.values())
    return {(h+i,a+j):((g[i,j]+SHRINK*v/n)/(ng+SHRINK) if conditional and ng else v/n)
            for (i,j),v in pooled.items()}


def assess(model,rows,conditional):
    losses=[];brier=[];totals=[];comeback=[]
    for _,_,_,h,a,x,y in rows:
        p=[0.,0.,0.];under=0.
        for (i,j),v in distribution(model,h,a,conditional).items():
            p[0 if i>j else 1 if i==j else 2]+=v
            if i+j<=2:under+=v
        actual=0 if x>y else 1 if x==y else 2
        losses.append(-math.log(max(1e-15,p[actual])))
        brier.append(math.fsum((v-(i==actual))**2 for i,v in enumerate(p)))
        totals.append((under-(x+y<=2))**2)
        if h!=a:
            t=0 if h<a else 2
            comeback.append((p[t]-(actual==t))**2)
    mean=lambda v:math.fsum(v)/len(v) if v else None
    return dict(n=len(rows),log_loss=mean(losses),brier=mean(brier),under25_brier=mean(totals),
                comeback_brier=mean(comeback),trailing_n=len(comeback))


def report(train,test):
    if not train or not test or max(r[0] for r in train)>=min(r[0] for r in test):
        raise ValueError("TEMPORAL_OVERLAP")
    model=fit(train)
    base=assess(model,test,False);candidate=assess(model,test,True)
    return dict(train_n=len(train),assessment_n=len(test),missing_ht_train=380-len(train),
                missing_ht_assessment=380-len(test),shrink=SHRINK,baseline=base,candidate=candidate,
                group_counts={str(k):sum(v.values()) for k,v in model[1].items()},
                historical_only=True,missingness_bias_not_ruled_out=True,
                red_card_or_xg_used=False,model_calibrated=False,automatic_promotion=False,
                verified_forward_sample_credit=0,positive_ev_verified=False,
                production_recommendations="DISABLED",status="HOLD")


if __name__=="__main__":
    print(json.dumps(report(fetch("2020-21"),fetch("2021-22")),sort_keys=True,allow_nan=False))
