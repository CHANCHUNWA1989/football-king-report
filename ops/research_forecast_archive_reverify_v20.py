"""Reverify one original archived run and link exact ledger forecasts.

Pins must be obtained independently from trusted workflow metadata. A local
archive, its saved verification JSON, and a caller's chosen pins do not establish
actual kickoff, official results, or production eligibility.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from .research_candidate_gap_v6 import stamp
from .research_live_intake_v4 import MAX_BYTES
from .research_forecast_proof_locator_v19 import locate, MEMBERS, MAX_COMPRESSED

LIMITS={"paired.json":8_388_608,"shadow.json":8_388_608,
        "slate.json":8_388_608,"research.sigstore.json":2_097_152}

def read_members(root, relative):
    if not isinstance(relative,str) or not re.fullmatch(
            r"[0-9]{4}/[0-9]{2}/[0-9]{2}/[1-9][0-9]{0,19}-[1-9][0-9]{0,9}",relative):
        raise ValueError("invalid archive path")
    datetime.strptime(relative[:10],"%Y/%m/%d")
    root=Path(root).absolute()
    current=Path(root.anchor)
    for part in (*root.parts[1:],*relative.split("/")):
        current=current/part
        if part==".." or current.is_symlink() or not current.is_dir():
            raise ValueError("unsafe archive directory")
    result={}
    for name in MEMBERS:
        path=current/name
        if path.is_symlink() or not path.is_file():
            raise ValueError("missing proof member")
        with path.open("rb") as f:packed=f.read(MAX_COMPRESSED+1)
        if not 0<len(packed)<=MAX_COMPRESSED:raise ValueError("compressed size limit")
        decoded_name=name[:-3]
        with gzip.GzipFile(fileobj=io.BytesIO(packed)) as f:
            body=f.read(LIMITS[decoded_name]+1)
        if not 0<len(body)<=LIMITS[decoded_name]:raise ValueError("decoded size limit")
        result[decoded_name]=body
    return result

# Only fixed, public-safe failure codes may leave the verifier.
REASONS=frozenset(("ATTESTATION_CLI_REJECTED","ATTESTATION_TOOL_UNAVAILABLE_OR_TIMEOUT",
    "ATTESTATION_PROCESS_TIMEOUT","CERTIFICATE_IDENTITY_MISMATCH","VERIFIED_SUBJECT_BYTES_MISMATCH",
    "VERIFIED_BUNDLE_MISMATCH","PROOF_BYTES_CHANGED_DURING_VERIFICATION",
    "INCONSISTENT_VERIFIED_ATTESTATIONS","MISSING_OR_AMBIGUOUS_TRUSTED_TLOG",
    "AUDIT_INPUT_OR_TOOL_ERROR","FRESH_VERIFICATION_FAILED"))

class VerificationFailure(ValueError):
    def __init__(self,reason):
        self.reason=reason if isinstance(reason,str) and reason in REASONS else "FRESH_VERIFICATION_FAILED"
        super().__init__(self.reason)

def verify_cli(proof,*,source_sha,workflow_sha,run_id,attempt):
    script=Path(__file__).with_name("forecast_provenance_audit.py").resolve()
    output=proof.parent/"audit.json"
    cmd=[sys.executable,str(script),"--proof",str(proof),"--source-sha",source_sha,
         "--workflow-sha",workflow_sha,"--run-id",run_id,"--attempt",attempt,
         "--output",str(output)]
    try:
        completed=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                 timeout=120,check=False)
    except subprocess.TimeoutExpired:
        raise VerificationFailure("ATTESTATION_PROCESS_TIMEOUT")
    if not output.is_file() or output.is_symlink():
        raise VerificationFailure("FRESH_VERIFICATION_FAILED")
    with output.open("rb") as f:raw=f.read(8_388_609)
    if not 0<len(raw)<=8_388_608:raise ValueError("audit report size")
    result=json.loads(raw)
    if completed.returncode!=0:
        raise VerificationFailure(result.get("reason") if isinstance(result,dict) else None)
    return result

def audit_run(raw,archive_root,relative,*,source_sha,workflow_sha):
    report={"schema":"forecast-archive-reverification-v20","status":"HOLD",
            "production_recommendations":"DISABLED","audit_completed":False,
            "matched_ledger_forecasts":0,"witness_before_recorded_kickoff_count":0,
            "authenticated_samples":0,"actual_kickoff_authenticated":False,
            "model_promotion_allowed":False,"cases":[]}
    try:
        if any(not isinstance(x,str) or not re.fullmatch("[0-9a-f]{40}",x)
               for x in (source_sha,workflow_sha)):
            raise ValueError("invalid commit pin")
        files=read_members(archive_root,relative)
        run,attempt=relative.split("/")[-1].split("-")
        now=datetime.now(timezone.utc)
        located=locate(raw,[(relative,files["paired.json"],True)],as_of=now.isoformat())
        links=[(c["key"],x) for c in located["cases"]
               if c["state"]=="MATCHING_PROOF_INPUT_CANDIDATE" for x in c["proof_candidates"]]
        if not links:raise ValueError("no exact ledger match in run")
        with tempfile.TemporaryDirectory(prefix="football-proof-") as temp:
            proof=Path(temp)/"proof";proof.mkdir(mode=0o700)
            for name,body in files.items():
                with (proof/name).open("xb") as f:f.write(body)
            verified=verify_cli(proof,source_sha=source_sha,workflow_sha=workflow_sha,
                                run_id=run,attempt=attempt)
            if any((proof/name).read_bytes()!=body for name,body in files.items()):
                raise ValueError("proof changed")
        digests={n:hashlib.sha256(b).hexdigest() for n,b in files.items()}
        if (verified.get("audit_completed") is not True
                or verified.get("signature_identity_and_subjects_verified") is not True
                or verified.get("production_recommendations")!="DISABLED"
                or verified.get("source_commit")!=source_sha or verified.get("workflow_commit")!=workflow_sha
                or verified.get("run_id")!=run or verified.get("run_attempt")!=attempt
                or verified.get("subject_sha256")!={n:digests[n] for n in ("paired.json","shadow.json","slate.json")}
                or verified.get("bundle_sha256")!=digests["research.sigstore.json"]):
            raise ValueError("verification binding mismatch")
        rows=verified["cases"]
        if not isinstance(rows,list) or len(rows)>10000:raise ValueError("invalid audit cases")
        indexed={r["pair_index"]:r for r in rows}
        if len(indexed)!=len(rows):raise ValueError("duplicate audit pair")
        cases=[]
        for key,link in links:
            r=indexed[link["pair_index"]]
            if r["case_id"]!=link["case_id"]:raise ValueError("audit case mismatch")
            witnessed=r.get("observed_before_recorded_kickoff") is True
            if witnessed:
                if (stamp(r["verified_tlog_utc"])!=stamp(verified["verified_tlog_utc"])
                    or stamp(r["verified_tlog_utc"])>now):
                    raise ValueError("invalid witness time")
            cases.append({"key":key,"case_id":link["case_id"],"pair_index":link["pair_index"],
                          "observed_before_recorded_kickoff":witnessed,
                          "verified_tlog_utc":r.get("verified_tlog_utc") if witnessed else None,
                          "authenticated":False})
        report.update(audit_completed=True,archive_run=relative,source_commit=source_sha,
                      workflow_commit=workflow_sha,ledger_sha256=hashlib.sha256(raw).hexdigest(),
                      subject_sha256=verified["subject_sha256"],bundle_sha256=verified["bundle_sha256"],
                      matched_ledger_forecasts=len(cases),cases=cases,
                      witness_before_recorded_kickoff_count=sum(c["observed_before_recorded_kickoff"] for c in cases))
    except VerificationFailure as exc:
        report["reason"]=exc.reason
    except (OSError,EOFError,subprocess.SubprocessError,KeyError,TypeError,ValueError,
            AttributeError,OverflowError,RecursionError):
        report["reason"]="MISSING_INVALID_OR_UNVERIFIED_ARCHIVE_INPUT"
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--archive-run",required=True)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--workflow-sha",required=True)
    a=p.parse_args()
    with (a.root/"evidence/settled.json").open("rb") as f:raw=f.read(MAX_BYTES+1)
    result=audit_run(raw,a.root/"forecast_provenance",a.archive_run,
                     source_sha=a.source_sha,workflow_sha=a.workflow_sha)
    print(json.dumps(result,sort_keys=True,allow_nan=False))
    return 0 if result["audit_completed"] else 2

if __name__=="__main__":
    raise SystemExit(main())
