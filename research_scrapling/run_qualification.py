"""One-shot research qualification, explicit failures and no model eligibility."""
import argparse
import json
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DOMAIN="football"
STEPS=[
    ("offline_historical",["test_historical_probe.py"]),
    ("offline_intake",["test_evidence_intake.py"]),
    
    ("parser",["collector.py","--self-test"]),
    ("disabled_config",["collector.py","--config",str(ROOT/"disabled.json"),"--output","disabled.json"]),
    ("single_probe",["historical_probe.py",DOMAIN,"historical.json"]),
    ("expanded_probe",["football_batch.py","expanded.json"]),
    ("intake",["evidence_intake.py",DOMAIN,"expanded.json","intake.json"])
]

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
        if a.offline_only and name in {"single_probe","expanded_probe","intake"}:
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
        report["steps"].append({"name":name,"status":"PASS" if code==0 else "FAIL","exit_code":code})
        failed=failed or code!=0
    report["finished_utc"]=datetime.now(timezone.utc).isoformat()
    report["qualification"]="FAILED" if failed else ("OFFLINE_ONLY_PASS" if a.offline_only else "HISTORICAL_RESEARCH_PASS")
    (dest/"qualification.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    return int(failed)
if __name__=="__main__":raise SystemExit(main())
