"""Offline CLI to turn an archived CI job log into an auditable JSON report.

Usage:
 python -m ops.research_archive_proof_ci_report_v1 --log job.log --output report.json
Exit 0: parsed successfully (NOT evidence acceptance).
Exit 2: invalid or missing summary (fail-closed).
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from ops.research_archive_proof_ci_audit_v1 import audit_archive_proof_ci_log

MAX_BYTES=5_000_000

def build_report(log_text:str)->dict:
    audit=audit_archive_proof_ci_log(log_text)
    return {"schema":"football-king-archive-proof-ci-report-v1",
            "audit":audit,"ci_evidence_gate_passed":False,
            "qualified_for_production":False,
            "production_recommendations":"DISABLED",
            "status":"HOLD"}

def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args(argv)
    try:
        source=Path(args.log)
        if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_BYTES:
            raise ValueError("invalid log file")
        log=source.read_text(encoding="utf-8")
        report=build_report(log)
        target=Path(args.output)
        if target.is_symlink() or target.exists() or not target.parent.is_dir():
            raise ValueError("output must be new regular file path")
        target.write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",
                          encoding="utf-8")
        print("ARCHIVE_PROOF_REPORT_WRITTEN",str(target))
        return 0
    except (OSError,ValueError,UnicodeError,json.JSONDecodeError) as exc:
        print("ARCHIVE_PROOF_REPORT_REJECTED",type(exc).__name__,file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
