"""Read-only candidate ledger diagnostics; never authenticates evidence."""
import argparse
from collections import Counter
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from .research_live_intake_v4 import decode, MAX_BYTES

LEAGUES=("bundesliga","epl","championship","laliga","seriea","ligue1")
TARGET=300

def stamp(s):
    if not isinstance(s,str):
        raise ValueError("timestamp required")
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.tzinfo is None:
        raise ValueError("naive timestamp")
    return t.astimezone(timezone.utc)

def vector(v):
    if not isinstance(v,list) or len(v)!=3 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in v) or abs(sum(v)-1)>.002:
        raise ValueError("invalid probability")
    return v

def audit(raw):
    report={"schema":"candidate-gap-audit-v6","status":"HOLD","production_recommendations":"DISABLED",
            "authenticated_samples":0,"remaining_authenticated_samples":TARGET,
            "model_promotion_allowed":False,"calibration_verified":False,"metrics_certified":False}
    try:
        doc=decode(raw)
        if doc["schema"]!="football-king-forward-research-1" or doc["production_recommendations"]!="DISABLED" or doc["results_independently_verified"] is not False:
            raise ValueError("unsafe ledger")
        rows=doc["samples"]
        if not isinstance(rows,list) or len(rows)>10000 or type(doc["n"]) is not int or doc["n"]!=len(rows):
            raise ValueError("invalid ledger count")
        checked=stamp(doc["checked_utc"])
        keys=set(); league=Counter(); ages=Counter(); gaps=Counter()
        queue=[]; losses=[]
        for row in rows:
            key=json.loads(row["key"])
            if not isinstance(key,list) or len(key)!=4 or not all(isinstance(s,str) and s.strip() for s in key) or key[0] not in LEAGUES or key[0]!=row["league"] or key[1]==key[2]:
                raise ValueError("invalid fixture identity")
            k,f,m=map(stamp,(row["kickoff_utc"],row["forecast_utc"],row["market_utc"]))
            canonical=(*key[:3],k.isoformat())
            if stamp(key[3])!=k or canonical in keys:
                raise ValueError("duplicate or mismatched fixture")
            keys.add(canonical)
            if not m<=f<k<checked:
                raise ValueError("invalid chronology")
            if row["production_recommendations"]!="DISABLED" or row["fixture_result_source_independently_verified"] is not False:
                raise ValueError("unsafe row claim")
            y=row["y"]
            if type(y) is not int or y not in (0,1,2):
                raise ValueError("invalid outcome")
            p,q=vector(row["p"]),vector(row["m"])
            league[row["league"]]+=1
            age=(f-m).total_seconds()/3600
            bucket="0-1h" if age<=1 else "1-6h" if age<=6 else "6-12h" if age<=12 else ">12h"
            ages[bucket]+=1
            missing=["INDEPENDENT_FORECAST_WITNESS_NOT_VERIFIED","INDEPENDENT_FINAL_RESULT_NOT_VERIFIED"]
            if not isinstance(row.get("source_fixture_identity"),dict) or not row["source_fixture_identity"]:
                missing.append("NO_SOURCE_FIXTURE_IDENTITY_FIELD")
            if not isinstance(row.get("score_ft"),list) or len(row["score_ft"])!=2 or any(type(v) is not int or not 0<=v<=30 for v in row["score_ft"]):
                missing.append("NO_EXACT_SCORE_FIELD")
            if age>6:
                missing.append("MARKET_CAPTURE_OLDER_THAN_6H")
            gaps.update(missing)
            queue.append({"fixture":list(canonical),"gaps":missing})
            losses.append((sum((v-(i==y))**2 for i,v in enumerate(p)),
                           sum((v-(i==y))**2 for i,v in enumerate(q)),
                           -math.log(max(p[y],1e-15)),-math.log(max(q[y],1e-15))))
        n=len(rows)
        metrics=dict(zip(("model_brier","market_brier","model_log_loss","market_log_loss"),
                         [sum(x[i] for x in losses)/n for i in range(4)])) if n else None
        report.update(structural_audit_passed=True,ledger_sha256=hashlib.sha256(raw).hexdigest(),
                      ledger_checked_utc=checked.isoformat(),candidate_count=n,by_league=dict(league),
                      market_age_buckets=dict(ages),evidence_gaps=dict(gaps),candidate_metrics=metrics,
                      metrics_use_unverified_recorded_outcomes=True,market_capture_not_same_cutoff=True,
                      age_threshold_is_diagnostic_only=True,recovery_queue=sorted(queue,key=lambda x:x["fixture"]))
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError):
        report.update(structural_audit_passed=False,reason="INVALID_OR_UNSAFE_CANDIDATE_LEDGER")
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,default=Path("evidence/settled.json"))
    a=p.parse_args()
    with a.ledger.open("rb") as stream:
        r=audit(stream.read(MAX_BYTES+1))
    print(json.dumps(r,sort_keys=True,allow_nan=False))
    return 0 if r.get("structural_audit_passed") else 2

if __name__=="__main__":
    raise SystemExit(main())
