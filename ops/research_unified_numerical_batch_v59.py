"""Bounded V39 batch + V56 strict scenario + V57 numerical validation.

Local replay and same-distribution sampling only; not independent forecasts,
authenticated evidence, calibrated uncertainty or executable EV.
"""
from .research_unified_cutoff_v39 import audit_batch
from .research_strict_analysis_receipt_v56 import report
from .research_numerical_crosscheck_v57 import crosscheck,DRAWS
from .research_unified_prematch_replay_v35 import digest

MAX_FIXTURES=8
MAX_DRAWS=2_000_000

def run(roster,records,*,cutoff,root="."):
    out={"schema":"unified-numerical-batch-v59","status":"HOLD",
         "production_recommendations":"DISABLED","batch_numerical_check_passed":False,
         "private_only":True,"public_output_allowed":False,
         "source_identity_authenticated":False,"external_timestamp_verified":False,
         "training_admission":False,"qualified_for_production":False,
         "verified_executable_ev":False,"independent_model_validation":False,
         "independent_oos_proven":False,"calibrated":False}
    try:
        if type(records) not in (list,tuple) or not 1<=len(records)<=MAX_FIXTURES:
            raise ValueError("batch budget")
        planned=0
        for r in records:
            if type(r) is not dict or type(r["forecasts"]) is not list or not 2<=len(r["forecasts"])<=8:
                raise ValueError("forecast budget")
            planned+=18*len(r["forecasts"])*DRAWS
        if planned>MAX_DRAWS:raise ValueError("draw budget")
        batch=audit_batch(roster,records,cutoff=cutoff,root=root)
        if (batch.get("cutoff_verified") is not True or batch.get("batch_replay_verified") is not True
                or batch.get("status")!="HOLD" or batch.get("production_recommendations")!="DISABLED"
                or any(batch.get(k) is not False for k in (
                    "source_identity_authenticated","external_timestamp_verified","training_admission",
                    "qualified_for_production","verified_executable_ev","roster_authenticated"))):
            raise ValueError("batch rejected")
        proofs=[]
        for r in sorted(records,key=lambda x:x["event_id"]):
            receipt=report(r,root=root)
            if (receipt.get("research_completed") is not True
                    or receipt.get("input_sha256")!=r["sha256"]
                    or receipt.get("scenario_count")!=18*len(r["forecasts"])
                    or receipt.get("status")!="HOLD"
                    or receipt.get("production_recommendations")!="DISABLED"
                    or receipt.get("private_only") is not True
                    or any(receipt.get(k) is not False for k in (
                        "source_identity_authenticated","external_timestamp_verified","training_admission",
                        "qualified_for_production","verified_executable_ev","public_output_allowed","calibrated"))):
                raise ValueError("receipt rejected")
            check=crosscheck(receipt,r,root=root)
            if (check.get("numerical_check_passed") is not True
                    or check.get("receipt_sha256")!=receipt["sha256"]
                    or check.get("scenario_count")!=receipt["scenario_count"]
                    or check.get("total_draws")!=DRAWS*receipt["scenario_count"]
                    or check.get("status")!="HOLD" or check.get("production_recommendations")!="DISABLED"
                    or check.get("private_only") is not True
                    or any(check.get(k) is not False for k in (
                        "independent_model_validation","training_admission","qualified_for_production",
                        "verified_executable_ev","public_output_allowed","calibrated"))):
                raise ValueError("numerical check rejected")
            proofs.append({"event_id":r["event_id"],"record_sha256":r["sha256"],
                           "receipt_sha256":receipt["sha256"],"crosscheck_sha256":check["sha256"],
                           "scenario_count":check["scenario_count"],"draw_count":check["total_draws"]})
        if sum(x["draw_count"] for x in proofs)!=planned:raise ValueError("draw count mismatch")
        result={**out,"batch_numerical_check_passed":True,"fixture_count":len(proofs),
                "cutoff_utc":batch["cutoff_utc"],"batch_sha256":batch["local_batch_sha256"],
                "total_draws":planned,"scenario_count":sum(x["scenario_count"] for x in proofs),
                "proofs":proofs}
        result["local_report_sha256"]=digest(result)
        return result
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError,RecursionError,IndexError):
        return {**out,"reason":"BATCH_BUDGET_OR_NUMERICAL_VALIDATION_REJECTED"}
