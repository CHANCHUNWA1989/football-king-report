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
    # Never fabricate an ID from a count; aggregate summaries do not carry it.
    return {"schema":"football-king-archive-proof-ci-audit-v1",
            "status":"HOLD","production_recommendations":"DISABLED",
            "model_promotion_allowed":False,
            "ledger_sha256":batch["ledger_sha256"],
            "candidate_fixtures":diag["candidate_fixtures"],
            "missing_witnesses":diag["missing_witnesses"],
            "missing_fixture_ids":None,
            "fixture_id_resolution":"REQUIRES_SOURCE_INVENTORY",
            "blockers":diag["blockers"],
            "remediation_tasks":plan["tasks"],
            "authenticated_samples":batch["authenticated_samples"],
            "evidence_authenticated":False,
            "note":"CI aggregate summaries are not independently verified source records."}
