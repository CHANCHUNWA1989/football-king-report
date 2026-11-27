"""Fail-closed preflight for a future historical replay sandbox.

A self-reported executor configuration is NOT evidence of OS isolation.
This module never launches code and never grants execution permission.
"""
from __future__ import annotations
import hashlib
from ops.research_quote_archive_v1 import _canonical
from ops.research_historic_replay_handoff_v1 import verify_historic_replay_handoff
from ops.research_historic_replay_policy_v1 import REQUIRED_CONTROLS

SCHEMA="football-king-historic-replay-preflight-v1"

def historical_replay_preflight(*,handoff:dict,snapshot:dict,record:dict,
                                plan:dict,executor_claims:dict|None=None)->dict:
    valid_handoff=verify_historic_replay_handoff(
        handoff,snapshot=snapshot,record=record,plan=plan)
    claims=executor_claims if isinstance(executor_claims,dict) else {}
    controls_match=(set(claims)==set(REQUIRED_CONTROLS)
                    and all(type(claims[k]) is type(v) and claims[k]==v
                            for k,v in REQUIRED_CONTROLS.items()))
    # Even an exact self-assertion cannot prove OS-enforced isolation.
    reason=("INVALID_HANDOFF" if not valid_handoff else
            "EXECUTOR_CONTROLS_NOT_MATCHED" if not controls_match else
            "OS_ISOLATION_UNATTESTED")
    result={"schema":SCHEMA,"status":"HOLD",
            "production_recommendations":"DISABLED",
            "qualified_for_production":False,"execution_permitted":False,
            "os_isolation_verified":False,
            "handoff_verified":bool(valid_handoff),
            "executor_claims_match_policy":bool(controls_match),
            "reason":reason,
            "handoff_sha256":handoff.get("sha256") if isinstance(handoff,dict) else None}
    result["sha256"]=hashlib.sha256(_canonical(result).encode()).hexdigest()
    return result

def verify_historical_replay_preflight(result:dict,*,handoff:dict,
                                       snapshot:dict,record:dict,plan:dict,
                                       executor_claims:dict|None=None)->bool:
    try:
        expected=historical_replay_preflight(
            handoff=handoff,snapshot=snapshot,record=record,
            plan=plan,executor_claims=executor_claims)
        return type(result) is dict and result==expected
    except (KeyError,TypeError,ValueError,AttributeError):
        return False
