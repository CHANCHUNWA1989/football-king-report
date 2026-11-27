"""Private in-memory V44 to V38 bridge, not a public signer input.

Recompute routing from original bytes; never accept caller-selected market
probabilities or a saved routing report. No network or persistence.
"""
from pathlib import Path
from .research_unified_market_route_v44 import route
from .research_prospective_fusion_v38 import capture as fusion_capture, canonical, sha, exact, manifest
from .research_missing_fixture_discovery_v16 import identity
from .research_candidate_gap_v6 import stamp
from .research_live_intake_v4 import decode, MAX_BYTES

FILES=("research_private_route_bridge_v45.py","research_unified_market_route_v44.py",
       "research_private_propline_v43.py","research_prospective_market_v41.py",
       "market_archive_guard.py")
def source_manifest():
    root=Path(__file__).resolve().parent
    files={}
    for name in FILES:
        p=root/name
        if p.is_symlink() or not p.is_file():raise ValueError("unsafe source")
        with p.open("rb") as f:b=f.read(MAX_BYTES+1)
        if not 0<len(b)<=MAX_BYTES:raise ValueError("source size")
        files[name]=sha(b)
    return {"routing":files,"fusion":manifest()}

def build(primary_raw,private_batches,history_raw,target,*,as_of):
    report={"schema":"private-route-bridge-summary-v45","status":"HOLD",
            "production_recommendations":"DISABLED","public_output_allowed":False,
            "source_authenticity_verified":False,"upstream_independence_proven":False,
            "external_time_witness_verified":False,"authenticated_samples":0,
            "training_admission":False,"model_promotion_allowed":False,
            "provider_calls_made":0,"private_receipts":0}
    try:
        before=source_manifest()
        exact(target,"league home away kickoff_utc")
        key=identity(target["league"],target["home"],target["away"],target["kickoff_utc"])
        now=stamp(as_of).isoformat()
        h=decode(history_raw);exact(h,"schema history")
        if h["schema"]!="private-fusion-history-v45":raise ValueError("history schema")
        selected,summary=route(primary_raw,private_batches,as_of=now)
        matches=[x for x in selected if identity(x["component"]["league"],x["component"]["home"],
                 x["component"]["away"],x["component"]["kickoff_utc"])==key]
        report["eligible_routes"]=summary["private_routes"]
        if len(matches)!=1:
            return None,{**report,"reason":"NO_UNAMBIGUOUS_ELIGIBLE_ROUTE"}
        chosen=matches[0];c=chosen["component"]
        raw=canonical({"schema":"prospective-fusion-input-v38","event_id":c["event_id"],
                       "league":c["league"],"home":c["home"],"away":c["away"],
                       "kickoff_utc":c["kickoff_utc"],"forecast_utc":now,
                       "market":c["market"],"history":h["history"]})
        r=fusion_capture(raw,as_of=now)
        if r["candidate"]["state"]!="RESEARCH_CANDIDATE" or source_manifest()!=before:
            raise ValueError("abstention or source change")
        bindings=[{"league":b["league"],"captured_utc":stamp(b["captured_utc"]).isoformat(),
                   "raw_sha256":sha(b["raw"])} for b in private_batches]
        result={"schema":"private-route-bridge-receipt-v45","status":"HOLD","private_only":True,
                "public_signer_allowed":False,"production_recommendations":"DISABLED",
                "source_authenticity_verified":False,"external_time_witness_verified":False,
                "authenticated_samples":0,"training_admission":False,"model_promotion_allowed":False,
                "as_of":now,"route":chosen["route"],"primary_raw_sha256":sha(primary_raw) if primary_raw is not None else None,
                "private_batch_bindings":sorted(bindings,key=lambda b:b["league"]),
                "history_raw_sha256":sha(history_raw),"source_manifest":before,
                "fusion_input_sha256":sha(raw),"fusion_receipt":r}
        result["receipt_sha256"]=sha(canonical(result))
        return result,{**report,"private_receipts":1}
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError,OSError):
        return None,{**report,"reason":"INVALID_PRIVATE_ROUTE_OR_HISTORY"}

def replay(receipt,primary_raw,private_batches,history_raw,target):
    try:
        result,_=build(primary_raw,private_batches,history_raw,target,as_of=receipt["as_of"])
        return result is not None and canonical(result)==canonical(receipt)
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError):
        return False
