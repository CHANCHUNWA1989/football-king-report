"""Actionable archive-proof remediation plan, without fabricating source evidence.

The plan is advisory and always fail-closed: no synthetic witness, kickoff,
upstream independence, or authenticated sample is created.
"""
from __future__ import annotations
from ops.research_archive_proof_blockers_v1 import diagnose_archive_proof

ACTIONS={
 "MISSING_VERIFIED_WITNESS":{
  "owner":"data-acquisition",
  "requirement":"Identify missing fixture and obtain timestamped external pre-kickoff witness",
  "acceptance":"Independent immutable witness link with recorded capture time and fixture ID"},
 "KICKOFF_NOT_AUTHENTICATED":{
  "owner":"fixture-provenance",
  "requirement":"Corroborate actual kickoff time from independent trustworthy providers",
  "acceptance":"Two independently attributable kickoff observations with timestamps"},
 "UPSTREAM_INDEPENDENCE_NOT_PROVEN":{
  "owner":"source-audit",
  "requirement":"Trace publisher upstream providers and reject mirrored feeds",
  "acceptance":"Documented distinct upstream provenance for both publishers"},
 "FORECAST_BATCH_INCOMPLETE":{
  "owner":"batch-integrity",
  "requirement":"Re-run archived forecast verification after missing source evidence is obtained",
  "acceptance":"Complete candidate set passes unchanged strict verification gate"},
 "NO_AUTHENTICATED_SAMPLES":{
  "owner":"oos-validation",
  "requirement":"Join authenticated pre-kickoff forecasts to independently verified results",
  "acceptance":"Nonzero authenticated paired samples; promotion still requires OOS thresholds"}
}

def plan_archive_proof_remediation(*,batch:dict,overlap:dict)->dict:
    diagnostic=diagnose_archive_proof(batch=batch,overlap=overlap)
    tasks=[{"blocker":name,**ACTIONS[name]} for name in diagnostic["blockers"]]
    return {"schema":"football-king-archive-proof-remediation-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "model_promotion_allowed":False,"diagnostic":diagnostic,
            "tasks":tasks,"external_evidence_collected":False,
            "ready_for_reverification":False,
            "note":"Planning output only; no new evidence has been authenticated."}
