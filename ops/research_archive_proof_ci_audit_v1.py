"""Parse GitHub Actions archive-proof summaries without treating them as verified evidence.

This module only extracts CI-reported aggregate facts. It cannot infer the
identity of a missing fixture from aggregate counts.
"""
from __future__ import annotations
import json
import re
from ops.research_archive_proof_remediation_v1 import plan_archive_proof_remediation

MARKERS=("V22_BATCH_VERIFICATION_SUMMARY","V23_EVIDENCE_OVERLAP_SUMMARY")
MAX_LOG_CHARS=5_000_000
MAX_SUMMARY_CHARS=200_000

def _extract(log:str,marker:str)->dict:
    matches=[]
    for line in log.splitlines():
        if marker not in line:
            continue
        after=line.split(marker,1)[1].strip()
        if len(after)>MAX_SUMMARY_CHARS:
            raise ValueError("oversized summary")
        value=json.loads(after)
        if type(value) is not dict:
            raise ValueError("summary must be object")
        matches.append(value)
    if len(matches)!=1:
        raise ValueError("expected exactly one "+marker)
    return matches[0]

def audit_archive_proof_ci_log(log:str)->dict:
    if type(log) is not str or len(log)>MAX_LOG_CHARS:
        raise ValueError("invalid log size")
    batch=_extract(log,MARKERS[0])
    overlap=_extract(log,MARKERS[1])
    plan=plan_archive_proof_remediation(batch=batch,overlap=overlap)
    diag=plan["diagnostic"]
    missing_ids=None
    resolution="REQUIRES_SOURCE_INVENTORY"
    if "V22_MISSING_WITNESS_KEYS" in log:
        missing=_extract(log,"V22_MISSING_WITNESS_KEYS")
        keys=missing.get("missing_keys")
        if (missing.get("ledger_sha256")!=batch["ledger_sha256"]
                or type(keys) is not list or any(type(k) is not str for k in keys)
                or len(set(keys))!=len(keys)
                or missing.get("count")!=len(keys)
                or len(keys)!=diag["missing_witnesses"]
                or missing.get("status")!="HOLD"):
            raise ValueError("invalid missing witness inventory")
        missing_ids=keys
        resolution="CI_SOURCE_INVENTORY_UNAUTHENTICATED"
    model_metrics=None
    if "V25_WITNESSED_DIAGNOSTICS_SUMMARY" in log:
        v25=_extract(log,"V25_WITNESSED_DIAGNOSTICS_SUMMARY")
        if (v25.get("ledger_sha256")!=batch["ledger_sha256"]
                or v25.get("model_promotion_allowed") is not False
                or v25.get("independent_oos_proven") is not False
                or v25.get("metrics_descriptive_only") is not True
                or v25.get("selection_bias_possible") is not True
                or v25.get("market_same_cutoff_proven") is not False
                or v25.get("weights_fitted") is not False
                or v25.get("authenticated_samples")!=batch["authenticated_samples"]):
            raise ValueError("unsafe or mismatched V25 diagnostic")
        subset=v25.get("witnessed_corroborated",{})
        paired=subset.get("paired",{})
        eligible=subset.get("eligible_count")
        paired_n=paired.get("n")
        models=paired.get("models")
        if (type(eligible) is not int or eligible<0
                or type(paired_n) is not int or paired_n!=eligible
                or eligible>overlap.get("witness_and_result_corroboration",eligible)
                or type(models) is not dict
                or not all(type(k) is str and type(v) is dict for k,v in models.items())):
            raise ValueError("invalid descriptive model cohort")
        model_metrics={"eligible_count":subset.get("eligible_count"),
                       "paired_n":paired.get("n"),
                       "models":paired.get("models"),
                       "metrics_descriptive_only":v25.get("metrics_descriptive_only"),
                       "selection_bias_possible":v25.get("selection_bias_possible")}

    # Never fabricate an ID from a count; aggregate summaries do not carry it.
    return {"schema":"football-king-archive-proof-ci-audit-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "model_promotion_allowed":False,
            "ledger_sha256":batch["ledger_sha256"],
            "candidate_fixtures":diag["candidate_fixtures"],
            "missing_witnesses":diag["missing_witnesses"],
            "missing_fixture_ids":missing_ids,
            "fixture_id_resolution":resolution,
            "blockers":diag["blockers"],
            "remediation_tasks":plan["tasks"],
            "authenticated_samples":batch["authenticated_samples"],
            "evidence_authenticated":False,
            "model_diagnostics":model_metrics,
            "note":"CI aggregate summaries are not independently verified source records."}
