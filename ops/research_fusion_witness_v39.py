"""Verify a future dedicated fusion witness using fresh GitHub attestation verification.

No signer is deployed here. Trust pins must be obtained independently of the
proof bundle. A successful witness concerns recorded kickoff, not actual kickoff
or the authenticity/completeness of the football inputs.
"""
import json
from datetime import datetime,timedelta,timezone
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from .research_live_intake_v4 import decode
from .research_candidate_gap_v6 import stamp
from .research_prospective_fusion_v38 import replay,sha,canonical

REPO="CHANCHUNWA1989/football-king-report"
REPO_URI="https://github.com/"+REPO
REF="refs/heads/main"
WORKFLOW=".github/workflows/football-king-fusion-witness.yml"
URI=REPO_URI+"/"+WORKFLOW+"@"+REF
SUBJECT="fusion-receipt.json"
MAX_OUTPUT=4*1024*1024
MAX_WITNESS_DELAY=timedelta(minutes=5)

def require(condition,reason):
    if not condition:raise ValueError(reason)

def certificate(source,workflow,run,attempt):
    return {"issuer":"https://token.actions.githubusercontent.com",
            "subjectAlternativeName":URI,"buildSignerURI":URI,"buildConfigURI":URI,
            "githubWorkflowRepository":REPO,"githubWorkflowRef":REF,
            "githubWorkflowSHA":workflow,"sourceRepositoryURI":REPO_URI,
            "sourceRepositoryDigest":source,"sourceRepositoryRef":REF,
            "buildSignerDigest":workflow,"buildConfigDigest":workflow,
            "runnerEnvironment":"github-hosted","sourceRepositoryIdentifier":"1411226578",
            "sourceRepositoryOwnerURI":"https://github.com/CHANCHUNWA1989",
            "sourceRepositoryOwnerIdentifier":"339931460",
            "runInvocationURI":REPO_URI+"/actions/runs/"+run+"/attempts/"+attempt}

def validate_verified_output(output,bundle,receipt_bytes,expected):
    require(isinstance(output,list) and len(output)==1 and isinstance(output[0],dict),"ambiguous verification")
    item=output[0]
    require(item["attestation"]["bundle"]==bundle,"bundle mismatch")
    r=item["verificationResult"]
    require(r["mediaType"]=="application/vnd.dev.sigstore.verificationresult+json;version=0.1","wrong verification schema")
    cert=r["signature"]["certificate"]
    require(isinstance(cert,dict) and all(cert.get(k)==v for k,v in expected.items()),"certificate mismatch")
    timestamps=r["verifiedTimestamps"]
    require(isinstance(timestamps,list) and len(timestamps)==1,"ambiguous witness")
    t=timestamps[0]
    require(t["type"]=="Tlog" and t["uri"]=="https://rekor.sigstore.dev","untrusted witness")
    witness=stamp(t["timestamp"])
    require(datetime.fromisoformat(t["timestamp"].replace("Z","+00:00")).utcoffset()==timedelta(0),"non UTC witness")
    s=r["statement"]
    require(s["_type"]=="https://in-toto.io/Statement/v1" and s["predicateType"]=="https://slsa.dev/provenance/v1","wrong statement")
    require(s["subject"]==[{"name":SUBJECT,"digest":{"sha256":sha(receipt_bytes)}}],"wrong subject bytes")
    return witness

def verify(raw,receipt_bytes,bundle_bytes,*,source_sha,workflow_sha,run_id,attempt,as_of):
    report={"schema":"prospective-fusion-external-witness-v39","status":"HOLD",
            "production_recommendations":"DISABLED","verification_completed":False,
            "observed_before_recorded_kickoff":False,"actual_kickoff_authenticated":False,
            "source_authenticity_verified":False,"independent_outcome_verified":False,
            "authenticated_samples":0,"training_admission":False,"model_promotion_allowed":False}
    try:
        for v in (source_sha,workflow_sha):
            require(isinstance(v,str) and re.fullmatch("[0-9a-f]{40}",v),"invalid commit pin")
        for v in (run_id,attempt):
            require(isinstance(v,str) and re.fullmatch("[1-9][0-9]{0,19}",v),"invalid run pin")
        now=stamp(as_of)
        receipt=decode(receipt_bytes);bundle=decode(bundle_bytes)
        replay(receipt,raw)
        require(receipt["candidate"]["state"]=="RESEARCH_CANDIDATE","no prediction to witness")
        expected=certificate(source_sha,workflow_sha,run_id,attempt)
        # Only private copies are passed to the verifier. Never trust saved output.
        with TemporaryDirectory(prefix="fusion-witness-") as tmp:
            p=Path(tmp)/SUBJECT;b=Path(tmp)/"fusion.sigstore.json"
            p.write_bytes(receipt_bytes);b.write_bytes(bundle_bytes)
            args=["gh","attestation","verify",str(p),"--bundle",str(b),"--repo",REPO,
                  "--signer-workflow",REPO+"/"+WORKFLOW,"--source-ref",REF,
                  "--source-digest",source_sha,"--signer-digest",workflow_sha,
                  "--deny-self-hosted-runners","--format","json"]
            result=subprocess.run(args,capture_output=True,timeout=30,shell=False,check=False)
            require(result.returncode==0,"verification rejected")
            require(isinstance(result.stdout,bytes) and 0<len(result.stdout)<=MAX_OUTPUT,"invalid verification output")
            # Reuse strict duplicate-key/nonfinite checks from the local intake.
            output=decode(b'{"output":'+result.stdout+b'}')["output"]
            witness=validate_verified_output(output,bundle,receipt_bytes,expected)
            require(p.read_bytes()==receipt_bytes and b.read_bytes()==bundle_bytes,"proof changed")
        f=stamp(receipt["forecast_utc"]);captured=stamp(receipt["receipt_clock_utc"])
        ko=stamp(receipt["fixture"][3])
        require(f<=captured<=witness<=now,"invalid witness chronology")
        require(witness<=captured+MAX_WITNESS_DELAY and witness<=ko-timedelta(minutes=10),"late witness")
        report.update(verification_completed=True,observed_before_recorded_kickoff=True,
                      verified_tlog_utc=witness.isoformat(),receipt_sha256=sha(receipt_bytes),
                      raw_input_sha256=sha(raw),bundle_sha256=sha(bundle_bytes),
                      source_commit=source_sha,workflow_commit=workflow_sha,run_id=run_id,run_attempt=attempt)
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError,RecursionError,OSError,subprocess.SubprocessError):
        report["reason"]="INVALID_OR_UNVERIFIED_FUSION_WITNESS"
    return report
