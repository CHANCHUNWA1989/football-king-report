"""Bounded fresh verification of original archive runs; never admit samples."""
import argparse
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
from .research_live_intake_v4 import MAX_BYTES
from .research_forecast_proof_locator_v19 import locate,scan
from .research_forecast_archive_reverify_v20 import audit_run
from .research_forecast_real_pilot_v21 import metadata,pins

MAX_RUNS=17
WORKERS=4
MAX_RETRIES=2
RETRYABLE=frozenset(("ATTESTATION_CLI_REJECTED","ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT",
                     "ATTESTATION_PROCESS_TIMEOUT"))

def run_one(raw,root,path):
    out={"archive_run":path,"state":"METADATA_REJECTED","cases":[]}
    try:
        run,attempt=path.split("/")[-1].split("-")
        source,workflow=pins(metadata(run,attempt),run,attempt)
        out.update(state="AUDIT_REJECTED",source_commit=source,workflow_commit=workflow)
        result=audit_run(raw,root,path,source_sha=source,workflow_sha=workflow)
        if result["audit_completed"] is not True:
            out["reason"]=result.get("reason","FRESH_VERIFICATION_FAILED")
            return out
        if (result["archive_run"]!=path
                or result["ledger_sha256"]!=hashlib.sha256(raw).hexdigest()
                or result["source_commit"]!=source or result["workflow_commit"]!=workflow):
            return out
        out.update(state="VERIFIED",cases=result["cases"])
    except (OSError,KeyError,TypeError,ValueError,AttributeError,OverflowError,subprocess.SubprocessError):
        pass
    return out

def batch(raw,root,loc,*,include_witness_keys=False):
    """Reconcile only links from the original exact-match locator; count fixtures once."""
    expected=defaultdict(set)
    candidate_keys=set()
    for c in loc["cases"]:
        if c["state"]!="MATCHING_PROOF_INPUT_CANDIDATE":continue
        candidate_keys.add(c["key"])
        for link in c["proof_candidates"]:
            expected[link["archive_run"]].add((c["key"],link["case_id"],link["pair_index"]))
    paths=sorted(expected,reverse=True)
    selected=paths[:MAX_RUNS]
    unattempted=paths[MAX_RUNS:]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results=list(pool.map(lambda path:run_one(raw,root,path),selected))
    # A retry is another full independent verification, not acceptance of a
    # previous success. Never retry explicit identity/hash/semantic failures.
    retries={}
    for i,(path,r) in enumerate(zip(selected,results)):
        if len(retries)>=MAX_RETRIES:break
        if r["state"]!="AUDIT_REJECTED" or r.get("reason") not in RETRYABLE:continue
        again=run_one(raw,root,path)
        if any(again.get(k)!=r.get(k) for k in ("source_commit","workflow_commit")):
            again={"archive_run":path,"state":"RETRY_PIN_MISMATCH","cases":[]}
        retries[path]={"initial_state":r["state"],"initial_reason":r["reason"],
                       "retry_state":again["state"],"retry_reason":again.get("reason")}
        results[i]=again
    statuses=Counter();witnessed=set();matched=set();detail=[]
    for path,r in zip(selected,results):
        state=r["state"];seen=set();good=set()
        if state=="VERIFIED":
            try:
                if r["archive_run"]!=path or not isinstance(r["cases"],list):
                    raise ValueError("wrong audit run")
                for c in r["cases"]:
                    item=(c["key"],c["case_id"],c["pair_index"])
                    if item in seen:raise ValueError("duplicate audit case")
                    seen.add(item)
                    if item in expected[path] and c["observed_before_recorded_kickoff"] is True:
                        good.add(c["key"])
                if not expected[path].issubset(seen):
                    raise ValueError("missing expected case")
            except (KeyError,TypeError,ValueError):
                state="LINK_RECONCILIATION_REJECTED";good=set()
        if state=="VERIFIED":
            matched.update(x[0] for x in expected[path])
            witnessed.update(good)
        statuses[state]+=1
        detail.append({"archive_run":path,"state":state,"witnessed_candidate_count":len(good),
                       "failure_reason":r.get("reason"),"retry":retries.get(path)})
    return {"schema":"forecast-batch-verification-v22","status":"HOLD","production_recommendations":"DISABLED",
            "candidate_runs":len(paths),"attempted_runs":len(selected),"unattempted_runs":len(unattempted),
            "unattempted_archive_runs":unattempted,
            "run_states":dict(statuses),"retry_count":len(retries),"candidate_fixtures":len(candidate_keys),
            "fresh_verified_linked_fixtures":len(matched),
            "unique_witness_before_recorded_kickoff_count":len(witnessed),
            "candidate_fixtures_without_verified_witness":len(candidate_keys-witnessed),
            "batch_passed":bool(paths and len(paths)==len(selected) and statuses["VERIFIED"]==len(paths) and witnessed==candidate_keys),
            "authenticated_samples":0,"actual_kickoff_authenticated":False,
            "model_promotion_allowed":False,"runs":detail,
            **({"witness_keys":sorted(witnessed),"ledger_sha256":hashlib.sha256(raw).hexdigest()} if include_witness_keys else {})}

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    with (a.root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    root=a.root/"forecast_provenance"
    loc=locate(raw,scan(root,raw),as_of=datetime.now(timezone.utc).isoformat())
    report=batch(raw,root,loc)
    print("V22_BATCH_VERIFICATION_SUMMARY "+json.dumps(report,sort_keys=True,allow_nan=False))
    return 0 if report["batch_passed"] else 2
if __name__=="__main__":
    raise SystemExit(main())
