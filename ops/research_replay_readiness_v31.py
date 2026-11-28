"""Point-in-time historical replay readiness; no model fitting or admission.

All clocks are recorded archive observations, not independently authenticated.
Thresholds are fixed research diagnostics, not qualification criteria.
"""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import re
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import candidates
from .research_final_observation_clock_v30 import recover
from .research_archive_score_recovery_v14 import archive_snapshots
from .research_two_publisher_recovery_v15 import secondary_snapshots
from .research_live_intake_v4 import MAX_BYTES

SINGLE="SINGLE_PUBLISHER_FINAL_CLOCK_CANDIDATE"
DUAL="TWO_PUBLISHER_FINAL_CLOCK_CANDIDATE"
DELAYS=(0,6,24)

def readiness(raw,report,*,as_of):
    now=stamp(as_of);rows=candidates(raw)
    if (report.get("schema")!="recorded-final-observation-clock-v30"
        or report.get("ledger_sha256")!=hashlib.sha256(raw).hexdigest()
        or report.get("status")!="HOLD" or report.get("production_recommendations")!="DISABLED"
        or report.get("training_admission") is not False
        or report.get("authenticated_samples")!=0):
        raise ValueError("invalid clock report")
    cases=report["cases"]
    by_key={x["key"]:x for x in cases}
    if len(cases)!=len(by_key) or set(by_key)!={r["key"] for r in rows.values()}:
        raise ValueError("clock roster mismatch")
    clocks=[];targets=[];excluded=Counter()
    for k,r in rows.items():
        c=by_key[r["key"]];state=c["state"]
        if c.get("result_availability_authenticated") is not False or c.get("training_admission") is not False:
            raise ValueError("unsafe clock case")
        if state not in (SINGLE,DUAL):
            excluded["NO_ACCEPTABLE_CLOCK"]+=1
            continue
        observed=stamp(c["recorded_final_observation_utc"])
        score=c["score_candidate"]
        if (not isinstance(score,list) or len(score)!=2
            or any(type(v) is not int or not 0<=v<=30 for v in score)
            or (0 if score[0]>score[1] else 1 if score[0]==score[1] else 2)!=r["y"]
            or not k[3]+timedelta(minutes=90)<=observed<=now):
            raise ValueError("invalid observed final")
        refs=c["references"]
        if not isinstance(refs,list) or len(refs)!=(2 if state==DUAL else 1):
            raise ValueError("wrong publisher count")
        providers={x["provider"] for x in refs}
        if len(providers)!=len(refs) or not providers<={"OpenLigaDB","thesportsdb"}:
            raise ValueError("wrong publisher roster")
        times=[]
        for ref in refs:
            t=stamp(ref["captured_utc"]);times.append(t)
            if (not k[3]+timedelta(minutes=90)<=t<=now
                or not isinstance(ref["decoded_sha256"],str)
                or not re.fullmatch("[0-9a-f]{64}",ref["decoded_sha256"])
                or not isinstance(ref["path"],str) or not ref["path"]
                or not isinstance(ref["provider_id"],str) or not ref["provider_id"]):
                raise ValueError("invalid archive reference")
        if max(times)!=observed:
            raise ValueError("clock not bound to final references")
        clocks.append((observed,k,state))
        f=stamp(r["forecast_utc"])
        if f>k[3]-timedelta(minutes=10):
            excluded["FORECAST_LEAD_LT_10_MIN"]+=1
            continue
        targets.append((f,k,state))
    clocks.sort();targets.sort()
    def scenario(dual,delay):
        available=[(t+timedelta(hours=delay),k) for t,k,s in clocks if not dual or s==DUAL]
        evaluated=[(f,k) for f,k,s in targets if not dual or s==DUAL]
        i=0;league=Counter();teams=Counter();counts=Counter();by_league=Counter()
        for f,k in evaluated:
            while i<len(available) and available[i][0]<f:
                _,prior=available[i];i+=1
                league[prior[0]]+=1
                teams[(prior[0],prior[1])]+=1
                teams[(prior[0],prior[2])]+=1
            by_league[k[0]]+=1
            counts["at_least_one_prior"]+=int(i>=1)
            counts["at_least_30_prior"]+=int(i>=30)
            counts["at_least_5_same_league"]+=int(league[k[0]]>=5)
            both=min(teams[(k[0],k[1])],teams[(k[0],k[2])])
            counts["both_teams_at_least_3_prior"]+=int(both>=3)
            counts["all_three_thresholds"]+=int(i>=30 and league[k[0]]>=5 and both>=3)
        return {"target_count":len(evaluated),"prior_pool_count":len(available),
                "counts":dict(counts),"by_league":dict(by_league)}
    return {"schema":"historical_replay_readiness-v31","status":"HOLD",
            "production_recommendations":"DISABLED","ledger_sha256":hashlib.sha256(raw).hexdigest(),
            "ledger_rows":len(rows),"clock_candidates":len(clocks),"forecast_targets":len(targets),
            "excluded_targets":dict(excluded),
            "scenarios":{scope:{str(d):scenario(scope=="dual_only",d) for d in DELAYS}
                         for scope in ("all_candidates","dual_only")},
            "thresholds_diagnostic_only":True,"archive_timestamps_authenticated":False,
            "selection_bias_possible":True,"authenticated_samples":0,
            "training_admission":False,"weights_fitted":False,"model_promotion_allowed":False}

def from_root(root,*,as_of):
    with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    rows=candidates(raw)
    report=recover(raw,archive_snapshots(root/"sources/live_germany/history",
        {k:r for k,r in rows.items() if k[0]=="bundesliga"}),
        secondary_snapshots(root/"sources/history",rows),as_of=as_of)
    return readiness(raw,report,as_of=as_of)

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    print(json.dumps(from_root(a.root,as_of=datetime.now(timezone.utc).isoformat()),sort_keys=True,allow_nan=False))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
