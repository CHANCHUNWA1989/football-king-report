"""Descriptive diagnostics on witnessed, corroborated original forecasts only.
No fitting, independent authentication, or production admission.
"""
from collections import defaultdict
from datetime import timedelta
import math
from random import Random
from .research_evidence_overlap_v23 import join,STATES
from .research_missing_fixture_discovery_v16 import candidates
from .research_candidate_calibration_v7 import metrics,valid_b,valid_c,LABELS
from .research_candidate_gap_v6 import stamp

def paired_day_interval(rows,field,*,draws=1000):
    groups=defaultdict(list)
    for r in rows:
        y=r["y"]
        diff=-math.log(max(r[field][y],1e-15))+math.log(max(r["m"][y],1e-15))
        groups[stamp(r["kickoff_utc"]).date()].append(diff)
    days=sorted(groups)
    if len(days)<10 or len(rows)<30:
        return {"status":"INSUFFICIENT_DESCRIPTIVE_SAMPLE","days":len(days),"n":len(rows)}
    rng=Random(20261127);values=[]
    for _ in range(draws):
        sample=[v for day in rng.choices(days,k=len(days)) for v in groups[day]]
        values.append(sum(sample)/len(sample))
    values.sort()
    return {"status":"DESCRIPTIVE_ONLY","days":len(days),"n":len(rows),
            "draws":draws,"lower":values[int(.025*(draws-1))],
            "upper":values[int(.975*(draws-1))]}

def diagnose(raw,result,proof):
    overlap=join(raw,result,proof)
    witnessed=set(proof["witness_keys"])
    rows={r["key"]:r for r in candidates(raw).values()}
    result_map={r["key"]:r["state"] for r in result["cases"]}
    def subset(states,age=None):
        eligible=[r for k,r in rows.items() if k in witnessed and result_map[k] in states
                  and (age is None or stamp(r["forecast_utc"])-stamp(r["market_utc"])<=timedelta(hours=age))]
        paired=[];missing=invalid=0
        for r in eligible:
            if not all(k in r for k in ("ab","ab_model","c","c_model")):
                missing+=1;continue
            if not valid_b(r["p"],r["ab"],r["ab_model"]) or not valid_c(r["p"],r["m"],r["c"],r["c_model"]):
                invalid+=1;continue
            paired.append(r)
        report=metrics(paired)
        # Compact aggregate output; calibration bins remain available in V7.
        for m in report["models"].values():m.pop("class_reliability",None)
        return {"eligible_count":len(eligible),"missing_challenger":missing,
                "invalid_challenger":invalid,"paired":report,
                "day_cluster_log_loss_delta_intervals":{k:paired_day_interval(paired,v)
                     for k,v in LABELS.items() if k!="market"}}
    return {"schema":"witnessed-model-diagnostics-v24","status":"HOLD",
            "production_recommendations":"DISABLED","ledger_sha256":overlap["ledger_sha256"],
            "forecast_batch_passed":overlap["forecast_batch_passed"],
            "witnessed_corroborated":subset(STATES),
            "witnessed_two_publisher":subset((STATES[1],)),
            "witnessed_corroborated_market_age_le_1h":subset(STATES,1),
            "authenticated_samples":0,"weights_fitted":False,"independent_oos_proven":False,
            "market_same_cutoff_proven":False,"model_promotion_allowed":False,
            "selection_bias_possible":True,"metrics_descriptive_only":True}
