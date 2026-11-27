"""Private paired candidate evaluation of original V48 runs, via V49 settlement.

No fitting, prediction alteration, network, publication or production admission.
Submitted runs and result snapshots are not proven complete or authenticated.
"""
from collections import Counter,defaultdict
import json
from random import Random
from .research_private_settlement_v49 import settle
from .research_private_run_store_v48 import MAX_RUN_BYTES
from .research_replay_attribution_v36 import losses
from .research_market_fusion_v37 import CAP,mix
from .research_candidate_gap_v6 import stamp
from .research_prospective_fusion_v38 import sha

MAX_RUNS=32
MAX_COHORT_BYTES=128*1024*1024
MODELS=("market","attack_defence","fixed_10pct","adaptive")
DRAWS=2000

def metrics(rows,name):
    if not rows:
        return {"n":0,"brier":None,"log_loss":None,"rps":None,
                "accuracy":None,"unique_top_count":0,"class_reliability":None}
    ll=[];br=[];rps=[];correct=0;unique=0
    bins=[[[] for _ in range(10)] for _ in range(3)]
    for row in rows:
        p=row[name];y=row["y"];a,b=losses(p,y);ll.append(a);br.append(b)
        rps.append(sum((sum(p[:i+1])-int(y<=i))**2 for i in (0,1))/2)
        top=[i for i,v in enumerate(p) if v==max(p)]
        unique+=int(len(top)==1);correct+=int(len(top)==1 and top[0]==y)
        for i,v in enumerate(p):bins[i][min(9,int(v*10))].append((v,int(y==i)))
    n=len(rows)
    return {"n":n,"brier":sum(br)/n,"log_loss":sum(ll)/n,"rps":sum(rps)/n,
            "accuracy":correct/n,"unique_top_count":unique,
            "class_reliability":[[{"bin":i,"n":len(g),"mean_p":sum(x for x,_ in g)/len(g),
                    "observed":sum(y for _,y in g)/len(g)} for i,g in enumerate(c) if g] for c in bins]}

def paired(rows,name):
    groups=defaultdict(list)
    for r in rows:
        a,b=losses(r[name],r["y"]);c,d=losses(r["market"],r["y"])
        groups[r["forecast_day"]].append((a-c,b-d))
    flat=[x for g in groups.values() for x in g];n=len(flat)
    out={"n":n,"forecast_days":len(groups),"log_loss_delta":sum(x[0] for x in flat)/n if n else None,
         "brier_delta":sum(x[1] for x in flat)/n if n else None,
         "interval":{"status":"INSUFFICIENT_SAMPLE","lower":None,"upper":None}}
    if n>=30 and len(groups)>=10:
        rng=Random(50);g=[groups[k] for k in sorted(groups)];draw=[]
        for _ in range(DRAWS):
            selected=rng.choices(g,k=len(g))
            draw.append(sum(sum(x[0] for x in v) for v in selected)/sum(map(len,selected)))
        draw.sort()
        out["interval"]={"status":"DESCRIPTIVE_DAY_CLUSTER_BOOTSTRAP","draws":DRAWS,
                         "lower":draw[49],"upper":draw[1949]}
    return out

def evaluate(runs,primary,secondary,*,as_of):
    now=stamp(as_of)
    if not isinstance(runs,list) or len(runs)>MAX_RUNS:raise ValueError("run roster")
    if any(not isinstance(b,bytes) or not 0<len(b)<=MAX_RUN_BYTES for b in runs):
        raise ValueError("invalid run bytes")
    if sum(map(len,runs))>MAX_COHORT_BYTES:raise ValueError("cohort size")
    # Require bounded reusable archive rosters: V49 checks source-specific caps.
    from .research_archive_score_recovery_v14 import MAX_FILES as pmax
    from .research_two_publisher_recovery_v15 import MAX_FILES as smax
    if not isinstance(primary,list) or not isinstance(secondary,list) or len(primary)>pmax or len(secondary)>smax:
        raise ValueError("result roster")
    seen=set();digests=set();states=Counter();rows=[]
    for raw in runs:
        digest=sha(raw)
        if digest in digests:raise ValueError("duplicate run")
        digests.add(digest)
        cases,report=settle(raw,primary,secondary,as_of=now.isoformat())
        if report["run_sha256"]!=digest or report["authenticated_samples"]!=0:
            raise ValueError("settlement mismatch")
        d=json.loads(raw);receipts={p["receipt"]["receipt_sha256"]:p["receipt"] for p in d["packets"]}
        if len(receipts)!=len(cases):raise ValueError("receipt roster mismatch")
        used=set()
        for c in cases:
            k=tuple(c["fixture"]);rid=c["receipt_sha256"]
            if k in seen or rid in used:raise ValueError("repeated fixture or receipt")
            seen.add(k);used.add(rid);r=receipts[rid]
            if tuple(r["fixture"])!=k:raise ValueError("fixture mismatch")
            states[c["state"]]+=1
            if c["state"]!="TWO_PUBLISHER_SCORE_CANDIDATE":continue
            y=c["outcome_candidate"]
            m=r["market_p"];a=r["model_p"];p=r["candidate"]["p"]
            rows.append({"y":y,"market":m,"attack_defence":a,"fixed_10pct":mix(a,m,CAP),
                         "adaptive":p,"forecast_day":stamp(r["forecast_utc"]).date().isoformat(),
                         "weight":r["candidate"]["weight"]})
    n=len(rows)
    return {"schema":"private-paired-fusion-evaluation-v50","status":"HOLD",
            "submitted_runs":len(runs),"submitted_fixtures":len(seen),"settlement_states":dict(states),
            "paired_candidates":n,"unsettled_or_excluded":len(seen)-n,
            "candidate_coverage":n/len(seen) if seen else None,
            "models":{k:metrics(rows,k) for k in MODELS},
            "paired_vs_market":{k:paired(rows,k) for k in MODELS if k!="market"},
            "mean_adaptive_weight":sum(r["weight"] for r in rows)/n if n else None,
            "zero_weight_count":sum(r["weight"]==0 for r in rows),
            "tie_rule":"tied top probability counts as not correct",
            "delta_definition":"model minus market; negative loss delta is better",
            "metrics_descriptive_only":True,"cohort_completeness_proven":False,
            "selection_bias_possible":True,"external_forecast_witness_verified":False,
            "actual_kickoff_authenticated":False,"regulation_score_authenticated":False,
            "independent_oos_proven":False,"authenticated_samples":0,
            "weights_fitted":False,"training_admission":False,"publication_allowed":False,
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
