"""Fail-closed historical replay isolation policy (specification, not execution).

This module deliberately does NOT run subprocesses, containers, historic Python,
network requests or arbitrary commands. A future executor must enforce the policy
at the OS/container boundary, not merely trust these declarations.
"""
from __future__ import annotations
import hashlib
from ops.research_quote_archive_v1 import _canonical
from ops.research_historic_source_attestation_v1 import attest_historical_source

REQUIRED_CONTROLS={
    "network":"none",
    "filesystem":"read_only",
    "run_as":"non_root",
    "privileges":"no_new_privileges",
    "capabilities":"drop_all",
    "seccomp":"enforced",
    "memory_mb":256,
    "cpu_seconds":30,
    "wall_seconds":60,
    "max_output_bytes":1048576,
    "secrets":"none",
    "production_access":False,
}
def historical_replay_plan(record: dict, *, historic_root: str) -> dict:
    attestation=attest_historical_source(record,historic_root=historic_root)
    plan={"schema":"football-king-historic-replay-plan-v1",
          "status":"HOLD","production_recommendations":"DISABLED",
          "execution_permitted":False,"executor_configured":False,
          "qualified_for_production":False,"attestation":attestation,
          "required_controls":dict(REQUIRED_CONTROLS)}
    plan["reason"]=("SOURCE_BYTES_MATCH_BUT_SANDBOX_NOT_CONFIGURED"
                    if attestation["historic_source_bytes_matched"]
                    else "SOURCE_ATTESTATION_FAILED")
    plan["sha256"]=hashlib.sha256(_canonical(plan).encode()).hexdigest()
    return plan

def verify_historical_replay_plan(plan: dict) -> bool:
    try:
        if not isinstance(plan,dict) or plan["schema"]!="football-king-historic-replay-plan-v1":
            return False
        if (plan["status"]!="HOLD" or plan["production_recommendations"]!="DISABLED"
            or plan["execution_permitted"] is not False
            or plan["executor_configured"] is not False
            or plan["qualified_for_production"] is not False
            or plan["required_controls"]!=REQUIRED_CONTROLS):
            return False
        expected={k:v for k,v in plan.items() if k!="sha256"}
        return hashlib.sha256(_canonical(expected).encode()).hexdigest()==plan["sha256"]
    except (ValueError,TypeError,KeyError,AttributeError):
        return False
