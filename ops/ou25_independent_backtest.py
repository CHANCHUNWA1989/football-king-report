"""Independent pre-match OU2.5 settlement and probability audit.

Only accepts predictions sealed before kickoff and independently supplied full-time
goals. Never interprets unverified model output as live betting advice.
"""
import argparse
import json
import math
from pathlib import Path

def audit(predictions, results, *, min_samples=100):
    if not isinstance(predictions,list) or not isinstance(results,list):
        raise ValueError("INVALID_DATA")
    lookup={}
    for item in results:
        if not isinstance(item,dict):
            continue
        key=item.get("fixture_id")
        if isinstance(key,str) and key and key not in lookup:
            lookup[key]=item
    settled=[]
    rejected=[]
    seen=set()
    for row in predictions:
        if not isinstance(row,dict):
            rejected.append({"reason":"INVALID_PREDICTION"})
            continue
        key=row.get("fixture_id")
        if not isinstance(key,str) or not key or key in seen:
            rejected.append({"fixture_id":key,"reason":"MISSING_OR_DUPLICATE_ID"})
            continue
        seen.add(key)
        outcome=lookup.get(key)
        if not outcome:
            rejected.append({"fixture_id":key,"reason":"NO_MATCHED_RESULT"})
            continue
        try:
            from datetime import datetime, timezone
            def parse(value):
                d=datetime.fromisoformat(value.replace("Z","+00:00"))
                if d.tzinfo is None:
                    raise ValueError()
                return d.astimezone(timezone.utc)
            sealed=parse(row["sealed_at_utc"])
            kickoff=parse(row["kickoff_utc"])
            if sealed>=kickoff:
                raise ValueError()
            home=outcome["home_goals"]
            away=outcome["away_goals"]
            p=row["probability_over"]
            if any(type(x) not in (int,float) or not math.isfinite(x) for x in (home,away,p)):
                raise ValueError()
            if int(home)!=home or int(away)!=away or min(home,away)<0 or not 0<=p<=1:
                raise ValueError()
            if outcome.get("status")!="FT":
                raise ValueError()
        except (KeyError,TypeError,ValueError,OverflowError,AttributeError):
            rejected.append({"fixture_id":key,"reason":"INVALID_OR_UNSEALED_EVIDENCE"})
            continue
        y=int(home+away>2)
        settled.append({"fixture_id":key,"p_over":p,"actual_over":y,
                        "brier":round((p-y)**2,8)})
    n=len(settled)
    brier=sum(x["brier"] for x in settled)/n if n else None
    baseline=sum(x["actual_over"] for x in settled)/n if n else None
    baseline_brier=baseline*(1-baseline) if n else None
    return {"schema":"ou25-independent-audit-v1","settled_count":n,
            "rejected_count":len(rejected),"minimum_samples":min_samples,
            "calibration_status":"INSUFFICIENT_EVIDENCE" if n<min_samples else "AUDIT_READY_NOT_VERIFIED",
            "mean_brier":round(brier,6) if brier is not None else None,
            "constant_rate_baseline_brier":round(baseline_brier,6) if baseline_brier is not None else None,
            "outperforms_constant_rate_baseline":brier<baseline_brier if n else None,
            "production_recommendations":"DISABLED","settled":settled,"rejected":rejected}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--predictions",required=True)
    parser.add_argument("--results",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    data=audit(json.loads(Path(args.predictions).read_text(encoding="utf-8")),
               json.loads(Path(args.results).read_text(encoding="utf-8")))
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
