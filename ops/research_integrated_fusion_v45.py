"""Private integrated research receipt pilot. No signing, network or file writes.

Rebuild market routes and final-history evidence from original local bytes.
Use only V30 ledger-linked finals; V32 supplemental provenance is not admitted.
Return private receipts separately from a count-only report.
"""
from collections import Counter
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from .research_candidate_gap_v6 import stamp
from .research_missing_fixture_discovery_v16 import candidates,identity
from .research_final_observation_clock_v30 import recover
from .research_archive_score_recovery_v14 import archive_snapshots
from .research_two_publisher_recovery_v15 import secondary_snapshots
from .research_calendar_gap_priority_v33 import selectors
from .research_live_intake_v4 import MAX_BYTES
from .research_unified_market_route_v44 import route
from .research_prospective_fusion_v38 import capture,canonical,sha,token,fingerprint,MAX_HISTORY

def history(raw,primary,secondary,*,as_of):
    now=stamp(as_of);rows=candidates(raw)
    report=recover(raw,primary,secondary,as_of=as_of)
    if report["ledger_sha256"]!=sha(raw) or report["training_admission"] is not False:
        raise ValueError("history inventory mismatch")
    by_key={r["key"]:k for k,r in rows.items()}
    if len(report["cases"])!=len(rows) or {c["key"] for c in report["cases"]}!=set(by_key):
        raise ValueError("history roster mismatch")
    staged=[];excluded=Counter()
    for c in report["cases"]:
        if c["recorded_final_observation_utc"] is None:
            excluded["NO_ELIGIBLE_FINAL_CLOCK"]+=1;continue
        k=by_key[c["key"]];t=stamp(c["recorded_final_observation_utc"])
        if not t+timedelta(hours=24)<now:
            excluded["WITHIN_24H_DELAY"]+=1;continue
        refs=c["references"]
        if not isinstance(refs,list) or len(refs) not in (1,2) or len({r["provider"] for r in refs})!=len(refs):
            raise ValueError("invalid final references")
        if len(refs)!=(2 if c["state"]=="TWO_PUBLISHER_FINAL_CLOCK_CANDIDATE" else 1):
            raise ValueError("final reference count mismatch")
        if c["state"] not in ("TWO_PUBLISHER_FINAL_CLOCK_CANDIDATE","SINGLE_PUBLISHER_FINAL_CLOCK_CANDIDATE"):
            raise ValueError("invalid final state")
        for ref in refs:
            if ref["provider"] not in ("OpenLigaDB","thesportsdb"):
                raise ValueError("invalid publisher")
            token(ref["provider_id"]);fingerprint(ref["decoded_sha256"])
            if not k[3]+timedelta(minutes=90)<=stamp(ref["captured_utc"])<=t:
                raise ValueError("invalid reference clock")
        last=max(refs,key=lambda r:(stamp(r["captured_utc"]),r["provider"]))
        if stamp(last["captured_utc"])!=t:raise ValueError("final clock mismatch")
        s=c["score_candidate"]
        if not isinstance(s,list) or len(s)!=2 or any(type(v) is not int or not 0<=v<=30 for v in s):
            raise ValueError("invalid final score")
        if (0 if s[0]>s[1] else 1 if s[0]==s[1] else 2)!=rows[k]["y"]:
            raise ValueError("final outcome mismatch")
        # Use original names and exact later publisher bytes as V38 evidence.
        # Retain all corroborating references separately in the private packet.
        league,h,a,ko=json.loads(c["key"])
        item={"league":league,"home":h,"away":a,"kickoff_utc":k[3].isoformat(),
              "observed_utc":t.isoformat(),"score":s,"source_id":last["provider"],
              "fixture_id":last["provider_id"],"evidence_sha256":last["decoded_sha256"]}
        staged.append((k,item,refs))
    ids=Counter((r["provider"],r["provider_id"]) for _,_,refs in staged for r in refs)
    slots=Counter((k[0],team,k[3]) for k,_,_ in staged for team in k[1:3])
    accepted=[]
    for k,item,refs in staged:
        if any(ids[(r["provider"],r["provider_id"])]!=1 for r in refs) or any(slots[(k[0],team,k[3])]!=1 for team in k[1:3]):
            excluded["HISTORY_IDENTITY_CONFLICT"]+=1;continue
        accepted.append((item,refs))
    if len(accepted)>MAX_HISTORY:raise ValueError("history budget exceeded")
    return accepted,{"ledger_rows":len(rows),"history_candidates":len(accepted),
                     "dual_publisher_candidates":sum(len(refs)==2 for _,refs in accepted),
                     "excluded":dict(excluded),"supplemental_history_included":False}

def prepare(raw,primary,secondary,market_raw,private_batches,*,as_of):
    now=stamp(as_of).isoformat()
    routes,routing=route(market_raw,private_batches,as_of=now)
    hist,summary=history(raw,primary,secondary,as_of=now)
    packets=[];states=Counter()
    for selected in routes:
        c=selected["component"]
        k=identity(c["league"],c["home"],c["away"],c["kickoff_utc"])
        # Keep the full frozen eligible pool to preserve V37 total support.
        if any(identity(r["league"],r["home"],r["away"],r["kickoff_utc"])==k for r,_ in hist):
            states["TARGET_HISTORY_COLLISION"]+=1;continue
        doc={name:c[name] for name in ("event_id","league","home","away","kickoff_utc","market")}
        doc.update(schema="prospective-fusion-input-v38",forecast_utc=now,history=[r for r,_ in hist])
        body=canonical(doc)
        receipt=capture(body,as_of=now)
        if receipt["candidate"]["state"]!="RESEARCH_CANDIDATE":
            states["NO_CANDIDATE"]+=1;continue
        packets.append({"raw_input":body,"receipt":receipt,"market_route":selected,
                        "history_references":[refs for _,refs in hist],"private_only":True})
        states["LOCAL_RECEIPT_CANDIDATE"]+=1
    return packets,{"schema":"private-integrated-fusion-pilot-v45","status":"HOLD",
                    "market_routing":routing,"history_inventory":summary,
                    "receipt_states":dict(states),"local_receipts":len(packets),
                    "provider_calls_made":0,"private_only":True,"publication_allowed":False,
                    "external_witnesses_created":0,"source_authenticity_verified":False,
                    "authenticated_samples":0,"training_admission":False,
                    "model_promotion_allowed":False,"production_recommendations":"DISABLED"}

def from_root(root,*,as_of):
    def read(path):
        if path.is_symlink() or not path.is_file():raise ValueError("unsafe file")
        with path.open("rb") as f:b=f.read(MAX_BYTES+1)
        if not 0<len(b)<=MAX_BYTES:raise ValueError("file size")
        return b
    raw=read(root/"evidence/settled.json")
    rows=candidates(raw);a,_=selectors(rows,primary=True);b,_=selectors(rows,primary=False)
    return prepare(raw,archive_snapshots(root/"sources/live_germany/history",a),
                   secondary_snapshots(root/"sources/history",b),
                   read(root/"market/latest.json"),[],as_of=as_of)
