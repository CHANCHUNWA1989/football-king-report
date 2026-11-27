"""Single offline entry point for the live research lifecycle.
No network, publication, automatic promotion, or external authentication.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from .research_live_intake_v4 import intake, decode, MAX_BYTES
from .research_live_evidence_v3 import settle, evaluate
from .research_live_calibration_v8 import calibrate
from .research_unified_live_v2 import digest, utc

MAX_CASES=1000

def safety():
    return {"schema":"unified-live-pipeline-v10","status":"HOLD",
            "production_recommendations":"DISABLED",
            "independent_oos_proven":False,"authenticated_samples":0,
            "model_promotion_allowed":False,"certified_ev":False}

def capture(raw_captures, policy, *, event_id, as_of, model_release, probability_only=False):
    """Receipt binds the exact adapter bytes and the normalized replay bundle."""
    report=intake(raw_captures,policy,event_id=event_id,as_of=as_of,
                  model_release=model_release,probability_only=probability_only)
    if not report.get("structural_intake_passed"):
        raise ValueError("intake rejected")
    receipt={"schema":"live-pipeline-receipt-v10","event_id":event_id,
             "as_of":utc(as_of).isoformat(),"model_release":model_release,
             "probability_only":probability_only,"intake":report}
    receipt["sha256"]=digest(receipt)
    return receipt

def replay(receipt, raw_captures, policy):
    """Recompute the entire intake from retained original envelopes, not just hashes."""
    try:
        expected=capture(raw_captures,policy,event_id=receipt["event_id"],
                         as_of=receipt["as_of"],model_release=receipt["model_release"],
                         probability_only=receipt["probability_only"])
        # Canonical JSON comparison also survives a JSON roundtrip of tuple fields.
        if digest(expected)!=digest(receipt):
            raise ValueError("receipt mismatch")
        return expected["intake"]["bundle"]
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError) as exc:
        raise ValueError("intake replay failed") from exc

def review(cases, *, model_release, train_start, train_cutoff, test_end, as_of):
    """Cases are locally supplied; timestamps, provider identities and coverage untrusted.
    Each receipt must replay from original bytes and local policy, then settle.
    No partial-cohort scoring after an invalid case.
    """
    out=safety()
    try:
        start,cut,end,now=map(utc,(train_start,train_cutoff,test_end,as_of))
        if not start<cut<end<=now:
            raise ValueError("invalid review window")
        if not isinstance(cases,list) or len(cases)>MAX_CASES:
            raise ValueError("invalid cohort size")
        pairs=[]
        seen=set()
        for case in cases:
            bundle=replay(case["receipt"],case["raw_captures"],case["policy"])
            if bundle["model_release"]!=model_release or bundle["event_id"] in seen:
                raise ValueError("mixed release or duplicate event")
            seen.add(bundle["event_id"])
            settled_at=utc(case["settled_at"])
            if settled_at>now:
                raise ValueError("future settlement")
            result=settle(bundle,case["final_observations"],as_of=settled_at.isoformat())
            pairs.append((bundle,result))
        cal=calibrate(pairs,model_release=model_release,train_start=start.isoformat(),
                      train_cutoff=cut.isoformat(),test_end=end.isoformat(),as_of=now.isoformat())
        summary=evaluate(pairs,model_release=model_release,cohort_start=start.isoformat(),
                         cohort_end=end.isoformat(),as_of=now.isoformat()) if pairs else None
        return {**out,"pipeline_replay_passed":True,"candidate_pairs":len(pairs),
                "probability_review":summary,"calibration_research":cal,
                "cohort_completeness_proven":False,"real_data_collection_performed":False}
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError,RecursionError):
        return {**out,"pipeline_replay_passed":False,"candidate_pairs":0,
                "reason":"INVALID_OR_INCOMPLETE_REVIEW"}

def main():
    parser=argparse.ArgumentParser(description="Offline private research cohort review")
    parser.add_argument("--input",type=Path,required=True)
    args=parser.parse_args()
    try:
        # Input is a local private JSON object; exact envelope bytes are hex encoded.
        with args.input.open("rb") as stream:
            request=decode(stream.read(MAX_BYTES+1))
        cases=request["cases"]
        if not isinstance(cases,list) or len(cases)>MAX_CASES:
            raise ValueError("invalid cohort size")
        for case in cases:
            raw=case["raw_captures"]
            if not isinstance(raw,list) or len(raw) not in (5,6):
                raise ValueError("invalid raw captures")
            case["raw_captures"]=[bytes.fromhex(v) for v in raw]
        report=review(cases,model_release=request["model_release"],train_start=request["train_start"],
                      train_cutoff=request["train_cutoff"],test_end=request["test_end"],
                      as_of=datetime.now(timezone.utc).isoformat())
    except (OSError,KeyError,ValueError,TypeError,AttributeError,RecursionError):
        report={**safety(),"pipeline_replay_passed":False,"reason":"INVALID_INPUT"}
    # Do not publish raw source payloads, quotes or fixture IDs.
    cal=report.get("calibration_research")
    if cal and "frozen_policy" in cal:
        policy=cal["frozen_policy"]
        cal["frozen_policy"]={k:v for k,v in policy.items() if k!="training_event_ids"}
        cal["frozen_policy"]["training_event_ids_redacted"]=True
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0 if report.get("pipeline_replay_passed") else 2

if __name__=="__main__":
    raise SystemExit(main())
