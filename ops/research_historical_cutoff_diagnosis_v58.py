"""V58 read-only historical cohort diagnosis; no authentication or model fit."""
from collections import defaultdict
import hashlib
import math
from .research_candidate_gap_v6 import audit,stamp,vector
from .research_live_intake_v4 import decode

AGE_LIMITS=(300,3600,21600)
LEAD_LIMITS=(3600,21600)

def diagnose(raw):
    out={"schema":"historical-cutoff-diagnosis-v58","status":"HOLD",
         "production_recommendations":"DISABLED","authenticated_samples":0,
         "independent_oos_proven":False,"market_same_cutoff_proven":False,
         "weights_fitted":False,"qualified_for_production":False,
         "descriptive_only":True,"diagnosis_completed":False}
    try:
        gate=audit(raw)
        if gate.get("structural_audit_passed") is not True:
            raise ValueError("ledger rejected")
        rows=decode(raw)["samples"]
        strata=defaultdict(list)
        missing_score=missing_identity=0
        for r in rows:
            p,m=vector(r["p"]),vector(r["m"])
            y=r["y"]
            k,f,t=map(stamp,(r["kickoff_utc"],r["forecast_utc"],r["market_utc"]))
            score=r.get("score_ft")
            if not isinstance(score,list) or len(score)!=2 or any(type(x) is not int or not 0<=x<=30 for x in score):
                missing_score+=1
            elif y!=(0 if score[0]>score[1] else 2 if score[0]<score[1] else 1):
                raise ValueError("score conflicts with outcome")
            if not isinstance(r.get("source_fixture_identity"),dict) or not r["source_fixture_identity"]:
                missing_identity+=1
            def loss(v):
                return sum((x-(i==y))**2 for i,x in enumerate(v)),-math.log(max(v[y],1e-15))
            pb,pl=loss(p);mb,ml=loss(m)
            row=(k.date().isoformat(),pb,pl,mb,ml)
            age=(f-t).total_seconds();lead=(k-f).total_seconds()
            strata["all"].append(row)
            for limit in AGE_LIMITS:
                if age<=limit:
                    strata["age_le_"+str(limit)].append(row)
            strata["league:"+r["league"]].append(row)
            age_bucket=next((str(x) for x in AGE_LIMITS if age<=x),"older")
            lead_bucket=next((str(x) for x in LEAD_LIMITS if lead<=x),"longer")
            strata["joint:"+age_bucket+":"+lead_bucket].append(row)
        def summarize(rs):
            n=len(rs)
            if not n:
                return {"n":0}
            totals=[sum(r[i] for r in rs) for i in range(1,5)]
            pb,pl,mb,ml=(x/n for x in totals)
            days=defaultdict(list)
            for r in rs:
                days[r[0]].append(r)
            b,l=[],[]
            for group in days.values():
                remaining=n-len(group)
                if remaining:
                    b.append((totals[0]-totals[2]-sum(r[1]-r[3] for r in group))/remaining)
                    l.append((totals[1]-totals[3]-sum(r[2]-r[4] for r in group))/remaining)
            return {"n":n,"days":len(days),"model_brier":pb,"market_brier":mb,
                    "model_log_loss":pl,"market_log_loss":ml,
                    "delta_brier":pb-mb,"delta_log_loss":pl-ml,
                    "leave_one_day_out_delta_brier":[min(b),max(b)] if b else None,
                    "leave_one_day_out_delta_log_loss":[min(l),max(l)] if l else None}
        for label in ("all",*("age_le_"+str(x) for x in AGE_LIMITS)):
            strata.setdefault(label,[])
        out.update(diagnosis_completed=True,ledger_sha256=hashlib.sha256(raw).hexdigest(),
                   candidate_count=len(rows),missing_exact_score=missing_score,
                   missing_source_identity=missing_identity,
                   cohorts={k:summarize(v) for k,v in sorted(strata.items())},
                   sensitivity_is_not_confidence_interval=True,
                   outcome_authentication_required=True)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,RecursionError):
        out["reason"]="INVALID_LEDGER_OR_OUTCOME"
    return out
