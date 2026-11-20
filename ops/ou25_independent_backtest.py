"""Independent pre-match OU2.5 settlement and probability audit.

Only accepts predictions sealed before kickoff and independently supplied full-time
goals. Never interprets unverified model output as live betting advice.
"""
import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

def _utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_UTC_INSTANT")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_UTC_INSTANT")
    return parsed.astimezone(timezone.utc)


def _training_baseline(baseline, sealed_instants):
    """No same-test-cohort frequencies: only an explicitly earlier training prior."""
    if baseline is None:
        return None
    if (not isinstance(baseline, dict)
            or type(baseline.get("probability_over")) not in (int, float)
            or not math.isfinite(baseline["probability_over"])
            or not 0 <= baseline["probability_over"] <= 1
            or type(baseline.get("sample_count")) is not int
            or baseline["sample_count"] < 30
            or not isinstance(baseline.get("source"), str)
            or not baseline["source"].strip()):
        raise ValueError("INVALID_TRAINING_ONLY_BASELINE")
    try:
        cutoff = _utc(baseline.get("training_cutoff_utc"))
    except (TypeError, ValueError, OverflowError, AttributeError) as exc:
        raise ValueError("INVALID_TRAINING_BASELINE_CUTOFF") from exc
    if sealed_instants and cutoff >= min(sealed_instants):
        raise ValueError("BASELINE_CUTOFF_NOT_BEFORE_EVALUATED_FORECASTS")
    # Timestamp and source are self-reported; not independently authenticated.
    return baseline["probability_over"]


def audit(predictions, results, *, min_samples=100, baseline=None):
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
    settled_sealed=[]
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
            sealed=_utc(row["sealed_at_utc"])
            kickoff=_utc(row["kickoff_utc"])
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
        settled_sealed.append(sealed)
    n=len(settled)
    brier=sum(x["brier"] for x in settled)/n if n else None
    prior=_training_baseline(baseline, settled_sealed)
    # The old code fitted its comparator to the held-out actuals: leakage.
    # Only the supplied, earlier training prior may now score the held-out set.
    baseline_brier=(sum((prior-x["actual_over"])**2 for x in settled)/n
                    if n and prior is not None else None)
    return {"schema":"ou25-independent-audit-v1","settled_count":n,
            "rejected_count":len(rejected),"minimum_samples":min_samples,
            "calibration_status":("INSUFFICIENT_EVIDENCE" if n<min_samples else
                                  "AUDIT_READY_NOT_VERIFIED" if prior is not None else
                                  "AUDIT_READY_BASELINE_MISSING"),
            "mean_brier":round(brier,6) if brier is not None else None,
            "constant_rate_baseline_brier":round(baseline_brier,6) if baseline_brier is not None else None,
            "outperforms_constant_rate_baseline":(
                brier<baseline_brier if baseline_brier is not None else None),
            "baseline_evidence_status":("SELF_REPORTED_PREMATCH_TRAINING_ONLY"
                                        if prior is not None else "MISSING_TRAINING_BASELINE"),
            "training_baseline_independently_authenticated":False,
            "training_baseline_sample_count":(baseline["sample_count"] if prior is not None else None),
            "training_baseline_cutoff_utc":(baseline["training_cutoff_utc"] if prior is not None else None),
            "market_odds_or_ev_verified":False,
            "production_recommendations":"DISABLED","settled":settled,"rejected":rejected}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--predictions",required=True)
    parser.add_argument("--results",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--training-baseline",default=None,
                        help="JSON prior from independent earlier training period, never the test outcomes")
    args=parser.parse_args()
    prior=(json.loads(Path(args.training_baseline).read_text(encoding="utf-8"))
           if args.training_baseline else None)
    data=audit(json.loads(Path(args.predictions).read_text(encoding="utf-8")),
               json.loads(Path(args.results).read_text(encoding="utf-8")),
               baseline=prior)
    dest=Path(args.output)
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

if __name__=="__main__":
    main()
