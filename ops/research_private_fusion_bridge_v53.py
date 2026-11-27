"""Single-fixture private research bridge from raw market inputs to V38.
No network, persistence, public signing, or training admission. Callers must
have permission to use the original inputs internally. The clock is untrusted.
"""
from .research_candidate_gap_v6 import stamp,LEAGUES
from .research_live_intake_v4 import decode
from .research_prospective_fusion_v38 import capture,canonical,exact,fixture,sha
from .research_unified_market_route_v44 import route

def prepare(primary_raw,private_batches,history_raw,*,target,as_of):
    exact(target,"league home away kickoff_utc")
    key=fixture(target)
    now=stamp(as_of).isoformat()
    history=decode(history_raw)
    exact(history,"history")
    if not isinstance(history["history"],list):
        raise ValueError("invalid history envelope")
    selected,routing=route(primary_raw,private_batches,as_of=now)
    report={"schema":"private-fusion-bridge-v53","status":"HOLD",
            "routing":routing,"local_receipts":0,"public_output_allowed":False,
            "source_authenticity_verified":False,"external_time_witness_verified":False,
            "authenticated_samples":0,"training_admission":False,
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
    matches=[row for row in selected if fixture(row["component"])==key]
    if len(matches)!=1:
        report["reason"]="NO_UNAMBIGUOUS_ELIGIBLE_TARGET"
        return None,report
    row=matches[0];c=row["component"]
    raw=canonical({"schema":"prospective-fusion-input-v38",
        **{k:c[k] for k in ("event_id","league","home","away","kickoff_utc","market")},
        "forecast_utc":now,"history":history["history"]})
    receipt=capture(raw,as_of=now)
    if receipt["candidate"]["state"]!="RESEARCH_CANDIDATE":
        report["reason"]="MODEL_ABSTAINED"
        return None,report
    # The private package is deliberately separate from the count-only report.
    # Its hashes are local integrity checks, not source authentication.
    package={"schema":"private-fusion-package-v53","private_only":True,
             "public_signing_allowed":False,"route":row["route"],
             "history_raw_sha256":sha(history_raw),"raw":raw,
             "receipt":receipt}
    report["local_receipts"]=1
    return package,report

def recheck(package,primary_raw,private_batches,history_raw,*,target,as_of):
    expected,report=prepare(primary_raw,private_batches,history_raw,target=target,as_of=as_of)
    if expected is None or package!=expected:
        raise ValueError("private package mismatch")
    return expected,report
