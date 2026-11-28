"""Unified, fail-closed historical research evidence admission.

No subprocess, sandbox, network, trading, or production enablement.
"""
from __future__ import annotations
import hashlib
from ops.research_quote_archive_v1 import _canonical
from ops.research_historic_replay_handoff_v1 import verify_historic_replay_handoff
from ops.research_historic_replay_preflight_v1 import historical_replay_preflight
from ops.research_historic_execution_report_gate_v1 import assess_historic_execution_report

SCHEMA="football-king-unified-historic-admission-v1"

def unified_historic_admission(*,record:dict,snapshot:dict,plan:dict,
                               handoff:dict,report:dict,
                               executor_claims:dict|None=None)->dict:
    handoff_valid=verify_historic_replay_handoff(
        handoff,snapshot=snapshot,record=record,plan=plan)
    preflight=historical_replay_preflight(
        handoff=handoff,snapshot=snapshot,record=record,plan=plan,
        executor_claims=executor_claims)
    report_gate=assess_historic_execution_report(
        report=report,handoff=handoff,snapshot=snapshot,record=record,
        plan=plan,executor_claims=executor_claims)
    report_valid=report_gate["report_structurally_valid"]
    result={"schema":SCHEMA,"status":"HOLD",
            "production_recommendations":"DISABLED",
            "qualified_for_production":False,
            "execution_permitted":False,
            "historic_replay_verified":False,
            "os_isolation_verified":False,
            "handoff_verified":bool(handoff_valid),
            "report_structurally_valid":bool(report_valid),
            "preflight_sha256":preflight["sha256"],
            "report_gate_sha256":report_gate["sha256"],
            "reason":("INVALID_HANDOFF" if not handoff_valid else
                      "INVALID_EXECUTOR_REPORT" if not report_valid else
                      "NO_INDEPENDENT_OS_ATTESTATION")}
    result["sha256"]=hashlib.sha256(_canonical(result).encode()).hexdigest()
    return result

def verify_unified_historic_admission(result:dict,*,record:dict,snapshot:dict,
                                     plan:dict,handoff:dict,report:dict,
                                     executor_claims:dict|None=None)->bool:
    try:
        expected=unified_historic_admission(
            record=record,snapshot=snapshot,plan=plan,handoff=handoff,
            report=report,executor_claims=executor_claims)
        return type(result) is dict and result==expected
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError):
        return False
