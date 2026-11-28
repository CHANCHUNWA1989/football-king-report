"""Untrusted sandbox report admission gate for historical replay research.

A report supplied by the executor is a claim, never independent OS attestation.
No code execution, production qualification or replay verification is granted.
"""
from __future__ import annotations
import hashlib
from ops.research_quote_archive_v1 import _canonical
from ops.research_historic_replay_preflight_v1 import (
    historical_replay_preflight,verify_historical_replay_preflight)

SCHEMA="football-king-historic-execution-report-gate-v1"
MAX_REPORT_BYTES=65536

def assess_historic_execution_report(*,report:dict,handoff:dict,snapshot:dict,
                                     record:dict,plan:dict,
                                     executor_claims:dict|None=None)->dict:
    preflight=historical_replay_preflight(
        handoff=handoff,snapshot=snapshot,record=record,
        plan=plan,executor_claims=executor_claims)
    base={"schema":SCHEMA,"status":"HOLD",
          "production_recommendations":"DISABLED",
          "qualified_for_production":False,"execution_permitted":False,
          "historic_replay_verified":False,"os_isolation_verified":False,
          "preflight_sha256":preflight["sha256"]}
    try:
        if not isinstance(report,dict):
            raise ValueError("invalid report")
        serialized=_canonical(report).encode("utf-8")
        if len(serialized)>MAX_REPORT_BYTES:
            raise ValueError("report too large")
        if set(report)!={"schema","handoff_sha256","exit_code",
                         "stdout_sha256","stderr_sha256","claimed_isolation"}:
            raise ValueError("unexpected report fields")
        if (report["schema"]!="football-king-historic-executor-report-v1"
            or report["handoff_sha256"]!=handoff.get("sha256")
            or type(report["exit_code"]) is not int
            or report["exit_code"]<0 or report["exit_code"]>255
            or type(report["claimed_isolation"]) is not bool):
            raise ValueError("invalid report fields")
        for name in ("stdout_sha256","stderr_sha256"):
            digest=report[name]
            if (type(digest) is not str or len(digest)!=64
                or any(ch not in "0123456789abcdef" for ch in digest)):
                raise ValueError("invalid digest")
        base["report_sha256"]=hashlib.sha256(serialized).hexdigest()
        base["report_structurally_valid"]=True
        base["reason"]=("PREFLIGHT_REJECTED" if not preflight["handoff_verified"]
                        else "UNTRUSTED_EXECUTOR_REPORT_NO_OS_ATTESTATION")
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        base["report_structurally_valid"]=False
        base["reason"]="INVALID_EXECUTOR_REPORT"
    base["sha256"]=hashlib.sha256(_canonical(base).encode()).hexdigest()
    return base
