"""One-shot research qualification, explicit failures and no model eligibility."""
import argparse
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
from evidence_intake import unique_object

ROOT=Path(__file__).resolve().parent
DOMAIN="football"
STEPS=[
    ("offline_historical",["test_historical_probe.py"]),
    ("offline_intake",["test_evidence_intake.py"]),
    ("offline_health",["test_source_health.py"]),
    ("offline_circuit",["test_circuit_policy.py"]),
    ("offline_checkpoint",["test_circuit_checkpoint.py"]),
    ("offline_runner",["test_qualification_reporting.py"]),
    ("offline_poll_policy",["test_poll_policy.py"]),
    ("offline_persistent_poll_policy",["test_persistent_poll_policy.py"]),
    ("offline_research_cache",["test_research_cache.py"]),
    ("parser",["collector.py","--self-test"]),
    ("disabled_config",["collector.py","--config",str(ROOT/"disabled.json"),"--output","disabled.json"]),
    ("single_probe",["historical_probe.py",DOMAIN,"historical.json"]),
    ("expanded_probe",["football_batch.py","expanded.json"]),
    ("intake",["evidence_intake.py",DOMAIN,"expanded.json","intake.json"]),
    ("health",["source_health.py",DOMAIN,"expanded.json","health.json"])
]
ARTIFACTS={"historical":"single_probe","expanded":"expanded_probe","intake":"intake","health":"health"}
MAX_REPORT_BYTES=100000

def finalize(dest,report,failed,offline):
    statuses={x["name"]:x["status"] for x in report["steps"]}
    errors=[]; messages=[]
    for name,step in ARTIFACTS.items():
        artifact=dest/(name+".json")
        try:
            if not artifact.exists():
                if statuses.get(step)=="PASS":raise ValueError("missing expected report")
                continue
            with artifact.open("rb") as stream:raw=stream.read(MAX_REPORT_BYTES+1)
            if len(raw)>MAX_REPORT_BYTES:raise ValueError("oversized report")
            data=json.loads(raw,object_pairs_hook=unique_object)
            if not isinstance(data,dict):raise ValueError("expected object")
            if data.get("status")!="HOLD" or data.get("live_trading")!="DISABLED" or data.get("production_recommendations")!="DISABLED" or data.get("model_input_allowed",False) is not False:
                raise ValueError("unsafe report")
            messages.append("EVIDENCE "+name+" "+json.dumps(data,sort_keys=True,allow_nan=False))
        except (ValueError,OSError,RecursionError,TypeError):
            errors.append(name)
    failed=failed or bool(errors)
    report["artifact_validation_errors"]=errors
    report["finished_utc"]=datetime.now(timezone.utc).isoformat()
    report["qualification"]="FAILED" if failed else ("OFFLINE_ONLY_PASS" if offline else "HISTORICAL_RESEARCH_PASS")
    (dest/"qualification.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print("QUALIFICATION "+json.dumps(report,sort_keys=True,allow_nan=False),flush=True)
    for message in messages:print(message,flush=True)
    for name in errors:print("EVIDENCE "+name+" INVALID",flush=True)
    return int(failed)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--offline-only",action="store_true")
    a=p.parse_args()
    dest=a.output.resolve()
    dest.mkdir(parents=True,exist_ok=True)
    if any(dest.iterdir()):
        p.error("evidence directory must be empty")
    report={"domain":DOMAIN,"status":"HOLD","production_recommendations":"DISABLED",
            "live_trading":"DISABLED","model_input_allowed":False,
            "started_utc":datetime.now(timezone.utc).isoformat(),"steps":[]}
    failed=False
    for name,args in STEPS:
        if a.offline_only and name in {"single_probe","expanded_probe","intake","health"}:
            report["steps"].append({"name":name,"status":"SKIPPED_OFFLINE"})
            continue
        if failed and name in {"single_probe","expanded_probe","intake"}:
            report["steps"].append({"name":name,"status":"SKIPPED_PREVIOUS_FAILURE"})
            continue
        try:
            with (dest/(name+".log")).open("wb") as log:
                r=subprocess.run([sys.executable,str(ROOT/args[0]),*args[1:]],cwd=dest,
                    stdout=log,stderr=subprocess.STDOUT,timeout=120,check=False)
            code=r.returncode
        except subprocess.TimeoutExpired:
            code=124
        except OSError:
            code=125
        report["steps"].append({"name":name,"status":"PASS" if code==0 else "FAIL","exit_code":code})
        failed=failed or code!=0
    return finalize(dest,report,failed,a.offline_only)
if __name__=="__main__":raise SystemExit(main())
