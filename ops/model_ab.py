"""Frozen, deterministic A/B model experiment. Never authorizes recommendations.

A = existing league Poisson/shrinkage probabilities. B = fixed 15% shrink
toward a uniform 1X2 prior. Same fixture and original prediction timestamp;
NO result, bookmaker prices, or contemporaneous outcome is accessed.
"""
import argparse
import json
import math
from pathlib import Path

SHRINK = 0.15
MODEL = "probability-shrink-to-uniform-fixed-0.15-v1"


def candidate(p):
    if (not isinstance(p,(list,tuple)) or len(p)!=3 or
            any(type(v) not in (int,float) or not math.isfinite(v)
                or v<0 or v>1 for v in p) or abs(sum(p)-1)>0.001):
        raise ValueError("INVALID_BASELINE_PROBABILITIES")
    new=[(1-SHRINK)*v+SHRINK/3 for v in p]
    total=sum(new)
    return [round(v/total,7) for v in new]


def apply(shadow):
    if not isinstance(shadow,dict) or shadow.get("production_recommendations")!="DISABLED":
        raise ValueError("UNSAFE_SHADOW_INPUT")
    rows=shadow.get("predictions")
    if not isinstance(rows,list):
        raise ValueError("INVALID_SHADOW_PREDICTIONS")
    for row in rows:
        if not isinstance(row,dict) or row.get("production_recommendations")!="DISABLED":
            raise ValueError("UNSAFE_SHADOW_EVENT")
        p=candidate([row["p_home"],row["p_draw"],row["p_away"]])
        row["ab_candidate_p_home"],row["ab_candidate_p_draw"],row["ab_candidate_p_away"]=p
        row["ab_model"]=MODEL
        row["ab_unvalidated"]=True
    shadow["ab_model"]=MODEL
    shadow["ab_experiment"]="SHADOW_ONLY"
    shadow["ab_preregistered_comparison"]="same_event_same_timestamp_poisson_A_vs_fixed_shrink_B"
    shadow["ab_candidate_count"]=len(rows)
    return {"schema":"football-king-ab-experiment-1",
            "as_of_utc":shadow["as_of_utc"],
            "status":"SHADOW_ONLY" if rows else "HOLD",
            "experiment":"A_poisson_baseline_vs_B_fixed_probability_shrink",
            "candidate_model":MODEL,
            "candidate_count":len(rows),
            "model_better_than_market_proven":False,
            "calibrated":False,
            "promotion_allowed":False,
            "production_recommendations":"DISABLED",
            "warning":"Fixed A/B research only; no promotion without out-of-sample evidence."}


def publish(site):
    site=Path(site)
    p=site/"shadow.json"
    shadow=json.loads(p.read_text(encoding="utf-8"))
    result=apply(shadow)
    p.write_text(json.dumps(shadow,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (site/"ab_status.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


if __name__=="__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("--site",default="app/site")
    cfg=arg.parse_args()
    print(json.dumps(publish(cfg.site),ensure_ascii=False))
