"""Validate an exported research receipt report against the verifier's guarded projection."""
from __future__ import annotations
from ops.research_receipt_report_projection_v1 import project_receipt_research_status

def inspect_exported_receipt_report(verification:dict, exported_report:dict)->dict:
    if type(exported_report) is not dict:
        raise ValueError("exported research report must be a mapping")
    expected=project_receipt_research_status(verification)
    if exported_report != expected:
        raise ValueError("exported report differs from guarded research projection")
    return {"export_report_matches_guarded_projection":True,
            "evidence_class":"offline-integrity-only",
            "authenticated_samples":0,"status":"HOLD",
            "model_promotion_allowed":False,
            "production_recommendations":"DISABLED"}
