"""Exact local capture replay before structural result mapping and evaluation.

Caller-provided raw inputs, hashes and source mappings remain unauthenticated.
Never confer real forward credit or change existing sealed probabilities.
"""
from deep_handicap_capture_replay import _replay_candidate
from deep_handicap_private_capture import _time
from deep_handicap_replay_bridge import bridge
from deep_handicap_forward_evaluation import evaluate

def assess(shadow,quotes,sealed,mapping,observations,*,expected_candidate_sha256,as_of_utc,data_kind):
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "exact_local_replay":False,"source_authenticated":False,
         "external_witness_verified":False,"true_forward_sample_count":0,
         "positive_expected_value_verified":False,"evaluation":None,
         "reason":"LOCAL_CAPTURE_REJECTED"}
    try:
        _replay_candidate(shadow,quotes,sealed,_time(as_of_utc))
        out["exact_local_replay"]=True
        mapped=bridge(sealed,mapping,observations,expected_candidate_sha256=expected_candidate_sha256,
                      as_of_utc=as_of_utc,data_kind=data_kind)
        row=mapped.get("evaluation_row")
        if row is None:
            return {**out,"reason":"RESULT_MAPPING_REJECTED"}
        result=evaluate([row],as_of_utc=as_of_utc)
        if (result["status"]!="HOLD" or result["production_recommendations"]!="DISABLED"
                or result["true_forward_sample_count"]!=0 or result["rejected"]
                or result["cohorts"][data_kind]["overall"]["n"]!=1
                or sum(v["overall"]["n"] for v in result["cohorts"].values())!=1):
            return {**out,"reason":"EVALUATION_REJECTED"}
        return {**out,"reason":"EXACT_LOCAL_REPLAY_AND_MAPPED_SETTLEMENT","evaluation":result}
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError,RecursionError):
        return out
