"""Private exact-input replay of archive-linked prospective forecasts.

No network, persistence, public signer, source authentication or promotion.
All receipts are local research only; callers must protect private outputs.
"""
from pathlib import Path
from .research_candidate_gap_v6 import stamp
from .research_prospective_fusion_v38 import canonical,sha,exact
from .research_private_route_bridge_v45 import build as bridge,source_manifest
from .research_integrated_fusion_v45 import history
from .research_supplemental_provenance_v46 import expanded_history,verify_ref
from .research_missing_fixture_discovery_v16 import identity
from .research_archive_score_recovery_v14 import MAX_FILES as PRIMARY_MAX
from .research_two_publisher_recovery_v15 import MAX_FILES as SECONDARY_MAX
from .research_live_intake_v4 import MAX_BYTES

MAX_TOTAL_ARCHIVE_BYTES=64*1024*1024
FILES=("research_archive_bound_replay_v47.py","research_integrated_fusion_v45.py",
       "research_supplemental_provenance_v46.py","research_supplemental_history_v32.py",
       "research_final_observation_clock_v30.py","research_historical_evidence_triage_v17.py",
       "research_archive_score_recovery_v14.py","research_two_publisher_recovery_v15.py",
       "source_publish_guard.py")
def manifest():
    root=Path(__file__).resolve().parent
    out={}
    for name in FILES:
        p=root/name
        if p.is_symlink() or not p.is_file():raise ValueError("unsafe source")
        with p.open("rb") as f:body=f.read(MAX_BYTES+1)
        if not 0<len(body)<=MAX_BYTES:raise ValueError("source size")
        out[name]=sha(body)
    return {"archive":out,"bridge":source_manifest()}

def freeze_archive(rows,limit,budget):
    if not isinstance(rows,(list,tuple)) or len(rows)>limit:raise ValueError("archive roster")
    bindings=[];frozen=[];seen=set()
    for item in rows:
        if not isinstance(item,(list,tuple)) or len(item)!=2:raise ValueError("archive entry")
        label,body=item
        if not isinstance(label,str) or not 0<len(label)<=1024 or label in seen:
            raise ValueError("archive label")
        if not isinstance(body,bytes) or not 0<len(body)<=MAX_BYTES:raise ValueError("archive bytes")
        budget-=len(body)
        if budget<0:raise ValueError("archive budget")
        seen.add(label);frozen.append((label,body))
        bindings.append({"label":label,"sha256":sha(body),"bytes":len(body)})
    return frozen,bindings,budget

def capture(ledger,primary,secondary,market_raw,private_batches,target,*,as_of,include_supplemental=False):
    summary={"schema":"archive-bound-replay-summary-v47","status":"HOLD",
             "production_recommendations":"DISABLED","private_only":True,
             "public_output_allowed":False,"authenticated_samples":0,
             "source_authenticity_verified":False,"external_time_witness_verified":False,
             "training_admission":False,"model_promotion_allowed":False,
             "provider_calls_made":0,"private_receipts":0}
    try:
        if type(include_supplemental) is not bool:raise ValueError("supplemental mode")
        before=manifest()
        exact(target,"league home away kickoff_utc")
        now=stamp(as_of).isoformat()
        a,ap,budget=freeze_archive(primary,PRIMARY_MAX,MAX_TOTAL_ARCHIVE_BYTES)
        b,bp,_=freeze_archive(secondary,SECONDARY_MAX,budget)
        recover=expanded_history if include_supplemental else history
        rows,stats=recover(ledger,a,b,as_of=now)
        archives={(provider,label,sha(body)):body
                  for provider,items in (("OpenLigaDB",a),("thesportsdb",b))
                  for label,body in items}
        for item,refs in rows:
            k=identity(item["league"],item["home"],item["away"],item["kickoff_utc"])
            if max(verify_ref(ref,k,item["score"],archives,stamp(now)) for ref in refs)!=stamp(item["observed_utc"]):
                raise ValueError("history reference clock")
        history_raw=canonical({"schema":"private-fusion-history-v45","history":[item for item,_ in rows]})
        inner,diagnostic=bridge(market_raw,private_batches,history_raw,target,as_of=now)
        summary["history_candidates"]=len(rows)
        if inner is None:return None,{**summary,"reason":"NO_ELIGIBLE_BRIDGE_RECEIPT"}
        if manifest()!=before:raise ValueError("source changed")
        receipt={"schema":"private-archive-bound-receipt-v47","status":"HOLD",
                 "production_recommendations":"DISABLED","private_only":True,
                 "public_signer_allowed":False,"authenticated_samples":0,
                 "source_authenticity_verified":False,"external_time_witness_verified":False,
                 "training_admission":False,"model_promotion_allowed":False,
                 "as_of":now,"include_supplemental":include_supplemental,
                 "ledger_sha256":sha(ledger),"primary_archives":ap,"secondary_archives":bp,
                 "history_reference_sha256":sha(canonical([refs for _,refs in rows])),
                 "source_manifest":before,"bridge_receipt":inner}
        receipt["receipt_sha256"]=sha(canonical(receipt))
        return receipt,{**summary,"private_receipts":1}
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError,OSError):
        return None,{**summary,"reason":"INVALID_ARCHIVE_OR_ROUTE"}

def replay(receipt,ledger,primary,secondary,market_raw,private_batches,target):
    try:
        result,_=capture(ledger,primary,secondary,market_raw,private_batches,target,
                         as_of=receipt["as_of"],include_supplemental=receipt["include_supplemental"])
        return result is not None and canonical(result)==canonical(receipt)
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError):
        return False
