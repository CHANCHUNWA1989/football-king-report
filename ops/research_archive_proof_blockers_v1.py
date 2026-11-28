"""Read-only diagnostics for archive-proof pilot verification blockers.

Never treats a CI pass or witness count as authenticated fixture evidence.
"""
from __future__ import annotations

def diagnose_archive_proof(*,batch:dict,overlap:dict)->dict:
    if not isinstance(batch,dict) or not isinstance(overlap,dict):
        raise ValueError("summaries must be dictionaries")
    required_batch=("candidate_fixtures","fresh_verified_linked_fixtures",
                    "authenticated_samples","actual_kickoff_authenticated",
                    "batch_passed","ledger_sha256")
    required_overlap=("authenticated_samples","actual_kickoff_authenticated",
                      "upstream_independence_proven","ledger_sha256",
                      "witness_and_two_publisher_exact_score")
    if any(k not in batch for k in required_batch) or any(k not in overlap for k in required_overlap):
        raise ValueError("incomplete summaries")
    for field in ("candidate_fixtures","fresh_verified_linked_fixtures","authenticated_samples"):
        if type(batch[field]) is not int or batch[field]<0:
            raise ValueError("invalid batch count")
    for field in ("authenticated_samples","witness_and_two_publisher_exact_score"):
        if type(overlap[field]) is not int or overlap[field]<0:
            raise ValueError("invalid overlap count")
    for source,fields in ((batch,("actual_kickoff_authenticated","batch_passed")),
                          (overlap,("actual_kickoff_authenticated","upstream_independence_proven"))):
        if any(type(source[f]) is not bool for f in fields):
            raise ValueError("invalid boolean")
    if (type(batch["ledger_sha256"]) is not str or
        batch["ledger_sha256"]!=overlap["ledger_sha256"]):
        raise ValueError("ledger mismatch")
    if batch["fresh_verified_linked_fixtures"]>batch["candidate_fixtures"]:
        raise ValueError("invalid witness count")
    missing=batch["candidate_fixtures"]-batch["fresh_verified_linked_fixtures"]
    blockers=[]
    if missing: blockers.append("MISSING_VERIFIED_WITNESS")
    if not batch["actual_kickoff_authenticated"] or not overlap["actual_kickoff_authenticated"]:
        blockers.append("KICKOFF_NOT_AUTHENTICATED")
    if not overlap["upstream_independence_proven"]:
        blockers.append("UPSTREAM_INDEPENDENCE_NOT_PROVEN")
    if not batch["batch_passed"]:
        blockers.append("FORECAST_BATCH_INCOMPLETE")
    if batch["authenticated_samples"]==0 or overlap["authenticated_samples"]==0:
        blockers.append("NO_AUTHENTICATED_SAMPLES")
    return {"schema":"football-king-archive-proof-blockers-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "model_promotion_allowed":False,
            "candidate_fixtures":batch["candidate_fixtures"],
            "verified_witnesses":batch["fresh_verified_linked_fixtures"],
            "missing_witnesses":missing,
            "exact_score_corroborations":overlap["witness_and_two_publisher_exact_score"],
            "blockers":blockers,
            "diagnostic_only":True}
