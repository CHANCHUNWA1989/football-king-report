"""One bounded, read-only real archive verification pilot for the research PR."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
from .research_live_intake_v4 import MAX_BYTES
from .research_forecast_proof_locator_v19 import from_root
from .research_forecast_archive_reverify_v20 import audit_run

REPO="CHANCHUNWA1989/football-king-report"
REPO_ID=1411226578
WORKFLOW=".github/workflows/football-king-iphone.yml"
MAX_METADATA_CALLS=3

def pins(meta,run,attempt):
    # The run REST response supplies the source pin, not a separately exposed
    # workflow SHA. For a direct, non-reusable main workflow we test the same
    # SHA as signer pin; the fresh signature verifier must actually agree.
    if (not isinstance(meta,dict) or str(meta.get("id"))!=run
            or str(meta.get("run_attempt"))!=attempt or meta.get("path")!=WORKFLOW
            or meta.get("head_branch")!="main" or meta.get("event")!="workflow_run"
            or meta.get("status")!="completed" or meta.get("conclusion")!="success"
            or meta.get("referenced_workflows")!=[]):
        raise ValueError("unexpected run identity")
    for name in ("repository","head_repository"):
        r=meta.get(name)
        if not isinstance(r,dict) or r.get("id")!=REPO_ID or r.get("full_name")!=REPO:
            raise ValueError("unexpected repository identity")
    sha=meta.get("head_sha")
    if not isinstance(sha,str) or not re.fullmatch("[0-9a-f]{40}",sha):
        raise ValueError("missing run head SHA")
    return sha,sha

def metadata(run,attempt):
    if not all(re.fullmatch("[1-9][0-9]{0,19}",v) for v in (run,attempt)):
        raise ValueError("invalid run")
    p=subprocess.run(["gh","api","--hostname","github.com",
        f"repos/{REPO}/actions/runs/{run}/attempts/{attempt}"],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,check=False,timeout=20)
    if p.returncode or not 0<len(p.stdout)<=1_000_000:
        raise ValueError("run metadata unavailable")
    return json.loads(p.stdout)

def pilot(root):
    out={"schema":"forecast-real-verification-pilot-v21","status":"HOLD",
         "production_recommendations":"DISABLED","authenticated_samples":0,
         "model_promotion_allowed":False,"metadata_calls":0,"verification_runs":0,
         "witness_before_recorded_kickoff_count":0,"pilot_passed":False,
         "workflow_pin_strategy":"DIRECT_MAIN_HEAD_SHA_HYPOTHESIS_VERIFIER_MUST_MATCH"}
    try:
        with (root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
        loc=from_root(root,as_of=datetime.now(timezone.utc).isoformat())
        paths=sorted({x["archive_run"] for c in loc["cases"]
            if c["state"]=="MATCHING_PROOF_INPUT_CANDIDATE" for x in c["proof_candidates"]},reverse=True)
        out["candidate_runs"]=len(paths)
        for path in paths[:MAX_METADATA_CALLS]:
            run,attempt=path.split("/")[-1].split("-")
            out["metadata_calls"]+=1
            try:source,workflow=pins(metadata(run,attempt),run,attempt)
            except (OSError,ValueError,TypeError,subprocess.SubprocessError):continue
            out.update(archive_run=path,source_commit=source,workflow_pin_candidate=workflow,
                       verification_runs=1)
            result=audit_run(raw,root/"forecast_provenance",path,
                             source_sha=source,workflow_sha=workflow)
            out["fresh_audit_completed"]=result["audit_completed"] is True
            out["witness_before_recorded_kickoff_count"]=result["witness_before_recorded_kickoff_count"]
            out["pilot_passed"]=bool(out["fresh_audit_completed"] and out["witness_before_recorded_kickoff_count"]>0)
            if not out["pilot_passed"]:out["reason"]="FRESH_VERIFICATION_OR_WITNESS_GATE_FAILED"
            return out
        out["reason"]="NO_ELIGIBLE_RUN_METADATA"
    except (OSError,KeyError,TypeError,ValueError,AttributeError,OverflowError,subprocess.SubprocessError):
        out["reason"]="PILOT_INPUT_OR_TOOL_ERROR"
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,default=Path("."))
    a=p.parse_args()
    result=pilot(a.root)
    print("V21_REAL_VERIFICATION_PILOT "+json.dumps(result,sort_keys=True,allow_nan=False))
    return 0 if result["pilot_passed"] else 2
if __name__=="__main__":
    raise SystemExit(main())
