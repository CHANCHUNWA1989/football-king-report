"""V43: fresh GitHub run metadata pins for the prospective witness verifier.

Only a direct, successful, manually dispatched main workflow is accepted.
The equal source/signer SHA is a hypothesis for a non-reusable workflow;
the cryptographic verifier must independently match it. No signer is deployed.
"""
import re
import subprocess
from .research_candidate_gap_v6 import stamp
from .research_live_intake_v4 import decode
from .research_fusion_witness_v39 import REPO, WORKFLOW, verify

MAX_METADATA=1_000_000
REPO_ID=1411226578
OWNER_ID=339931460

def pin_id(v):
    if not isinstance(v,str) or not re.fullmatch(r"[1-9][0-9]{0,19}",v):
        raise ValueError("invalid run identity")
    return v

def resolve(meta,*,run_id,attempt,as_of):
    pin_id(run_id);pin_id(attempt)
    if (not isinstance(meta,dict) or type(meta.get("id")) is not int
        or str(meta["id"])!=run_id or type(meta.get("run_attempt")) is not int
        or str(meta["run_attempt"])!=attempt or meta.get("path")!=WORKFLOW
        or meta.get("head_branch")!="main" or meta.get("event")!="workflow_dispatch"
        or meta.get("status")!="completed" or meta.get("conclusion")!="success"
        or meta.get("referenced_workflows")!=[]):
        raise ValueError("unexpected workflow run")
    for name in ("repository","head_repository"):
        r=meta.get(name)
        if (not isinstance(r,dict) or r.get("id")!=REPO_ID or r.get("full_name")!=REPO
            or not isinstance(r.get("owner"),dict) or r["owner"].get("id")!=OWNER_ID):
            raise ValueError("unexpected repository identity")
    sha=meta.get("head_sha")
    if not isinstance(sha,str) or not re.fullmatch("[0-9a-f]{40}",sha):
        raise ValueError("invalid source commit")
    started,updated,now=map(stamp,(meta["run_started_at"],meta["updated_at"],as_of))
    if not started<=updated<=now:
        raise ValueError("invalid metadata chronology")
    return {"source_sha":sha,"workflow_sha":sha,"run_id":run_id,"attempt":attempt,
            "started":started,"updated":updated}

def metadata(run_id,attempt):
    pin_id(run_id);pin_id(attempt)
    result=subprocess.run(["gh","api","--hostname","github.com",
        f"repos/{REPO}/actions/runs/{run_id}/attempts/{attempt}"],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20,check=False,shell=False)
    if result.returncode!=0 or not isinstance(result.stdout,bytes) or not 0<len(result.stdout)<=MAX_METADATA:
        raise ValueError("metadata unavailable")
    return decode(result.stdout)

def verify_with_fresh_pins(raw,receipt,bundle,*,run_id,attempt,as_of):
    report={"schema":"fusion-witness-pin-gate-v43","status":"HOLD",
            "production_recommendations":"DISABLED","metadata_resolved":False,
            "witness_verified":False,"actual_kickoff_authenticated":False,
            "source_authenticity_verified":False,"authenticated_samples":0,
            "training_admission":False,"model_promotion_allowed":False}
    try:
        p=resolve(metadata(run_id,attempt),run_id=run_id,attempt=attempt,as_of=as_of)
        report["metadata_resolved"]=True
        report["signer_pin_strategy"]="DIRECT_MAIN_HEAD_SHA_MUST_MATCH_CERTIFICATE"
        v=verify(raw,receipt,bundle,source_sha=p["source_sha"],workflow_sha=p["workflow_sha"],
                 run_id=run_id,attempt=attempt,as_of=as_of)
        if (v.get("verification_completed") is not True
            or v.get("observed_before_recorded_kickoff") is not True
            or v.get("source_commit")!=p["source_sha"] or v.get("workflow_commit")!=p["workflow_sha"]
            or v.get("run_id")!=run_id or v.get("run_attempt")!=attempt
            or not p["started"]<=stamp(v["verified_tlog_utc"])<=p["updated"]):
            raise ValueError("witness or chronology rejected")
        report.update(witness_verified=True,witness=v)
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError,OSError,subprocess.SubprocessError):
        report["reason"]="METADATA_OR_WITNESS_REJECTED"
    return report

def audit_directory(proof,*,run_id,attempt,as_of):
    """Reverify downloaded original proof bytes; never consume saved audit JSON."""
    from pathlib import Path
    from .research_fusion_signer_v40 import read
    root=Path(proof).absolute()
    if any(p.is_symlink() for p in (root,*root.parents)) or not root.is_dir():
        raise ValueError("unsafe proof directory")
    pin_id(run_id);pin_id(attempt)
    raw,receipt,bundle=(read(root/name) for name in
        ("fusion-input.json","fusion-receipt.json","fusion.sigstore.json"))
    return verify_with_fresh_pins(raw,receipt,bundle,run_id=run_id,attempt=attempt,as_of=as_of)

def main():
    import argparse
    import json
    from datetime import datetime,timezone
    p=argparse.ArgumentParser(description="Independent research witness recheck")
    p.add_argument("--proof",required=True)
    p.add_argument("--run-id",required=True)
    p.add_argument("--attempt",required=True)
    a=p.parse_args()
    try:
        report=audit_directory(a.proof,run_id=a.run_id,attempt=a.attempt,
                               as_of=datetime.now(timezone.utc).isoformat())
    except (ValueError,OSError,TypeError,KeyError,AttributeError):
        report={"schema":"fusion-witness-pin-gate-v43","status":"HOLD",
                "production_recommendations":"DISABLED","witness_verified":False,
                "authenticated_samples":0,"training_admission":False,
                "model_promotion_allowed":False,"reason":"INVALID_PROOF_DIRECTORY"}
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0 if report["witness_verified"] is True else 1

if __name__=="__main__":
    raise SystemExit(main())
