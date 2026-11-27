"""Fail-closed handoff envelope for a future isolated historical replay executor.

This is a data-only envelope: it does not launch or configure an executor.
"""
from __future__ import annotations
import hashlib
from ops.research_quote_archive_v1 import _canonical
from ops.research_historic_source_snapshot_v1 import verify_historic_source_snapshot
from ops.research_historic_replay_policy_v1 import (
    REQUIRED_CONTROLS,verify_historical_replay_plan)

SCHEMA="football-king-historic-replay-handoff-v1"

def create_historic_replay_handoff(*,snapshot:dict,record:dict,plan:dict)->dict:
    if not verify_historic_source_snapshot(snapshot,record):
        raise ValueError("unverified source snapshot")
    if not verify_historical_replay_plan(plan):
        raise ValueError("invalid isolation policy")
    if (plan["reason"]!="SOURCE_BYTES_MATCH_BUT_SANDBOX_NOT_CONFIGURED"
        or plan["attestation"].get("historic_source_bytes_matched") is not True):
        raise ValueError("source attestation failed")
    envelope={"schema":SCHEMA,"status":"HOLD",
              "production_recommendations":"DISABLED",
              "execution_permitted":False,"executor_configured":False,
              "qualified_for_production":False,
              "snapshot_sha256":snapshot["sha256"],
              "archive_sha256":record["sha256"],
              "policy_sha256":plan["sha256"],
              "required_controls":dict(REQUIRED_CONTROLS),
              "source_manifest_sha256":snapshot["source_manifest_sha256"]}
    envelope["sha256"]=hashlib.sha256(_canonical(envelope).encode()).hexdigest()
    return envelope

def verify_historic_replay_handoff(envelope:dict,*,snapshot:dict,
                                   record:dict,plan:dict)->bool:
    try:
        if not isinstance(envelope,dict):
            return False
        if (envelope["schema"]!=SCHEMA or envelope["status"]!="HOLD"
            or envelope["production_recommendations"]!="DISABLED"
            or envelope["execution_permitted"] is not False
            or envelope["executor_configured"] is not False
            or envelope["qualified_for_production"] is not False
            or envelope["required_controls"]!=REQUIRED_CONTROLS):
            return False
        if not verify_historic_source_snapshot(snapshot,record):
            return False
        if not verify_historical_replay_plan(plan):
            return False
        if (plan["reason"]!="SOURCE_BYTES_MATCH_BUT_SANDBOX_NOT_CONFIGURED"
            or plan["attestation"].get("historic_source_bytes_matched") is not True):
            return False
        if (envelope["snapshot_sha256"]!=snapshot["sha256"]
            or envelope["archive_sha256"]!=record["sha256"]
            or envelope["policy_sha256"]!=plan["sha256"]
            or envelope["source_manifest_sha256"]!=snapshot["source_manifest_sha256"]):
            return False
        payload={k:v for k,v in envelope.items() if k!="sha256"}
        return hashlib.sha256(_canonical(payload).encode()).hexdigest()==envelope["sha256"]
    except (KeyError,TypeError,ValueError,AttributeError):
        return False
