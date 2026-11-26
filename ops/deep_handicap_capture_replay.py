"""Replay a locally claimed deep-line capture before evaluating result claims.

This is a private in-memory consistency check, not an externally witnessed
archive. It never retrieves data, persists raw quotes or grants forward credit.
"""
import copy
from deep_handicap_private_capture import capture, _time, _digest
from deep_handicap_forward_evaluation import evaluate

def replay_and_evaluate(shadow, quote_report, sealed, results, *, as_of_utc):
    out={"status":"HOLD","production_recommendations":"DISABLED",
         "locally_replayed":False,"external_witness_verified":False,
         "authenticated_forward_samples":0,"positive_ev_verified":False,
         "evaluation":None,"reason":"CAPTURE_REPLAY_REJECTED"}
    try:
        if not isinstance(sealed,dict):return out
        original=sealed["candidate"]
        if not isinstance(original,dict) or "results" in original:return out
        recorded=_time(original["evidence"]["recorded_capture_utc"])
        as_of=_time(as_of_utc)
        if recorded>as_of:return out
        if _digest(original)!=sealed.get("candidate_sha256"):return out
        replay=capture(shadow,quote_report,now=recorded)
        if replay.get("candidate") is None or replay!=sealed:return out
        if not isinstance(results,list) or not 2<=len(results)<=10:return out
        # Keep original forecasts immutable; settlement is a derived record.
        row=copy.deepcopy(original)
        row["results"]=copy.deepcopy(results)
        report=evaluate([row],as_of_utc=as_of_utc)
        out["locally_replayed"]=True
        out["evaluation"]=report
        n=report["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"]
        out["reason"]="LOCAL_REPLAY_AND_STRUCTURAL_SETTLEMENT" if n==1 else "RESULT_CLAIMS_REJECTED"
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
        return out
    return out
