"""Research-only receipt report projection; never upgrade offline checks to authentication."""
from __future__ import annotations

def project_receipt_research_status(verification:dict)->dict:
    if type(verification) is not dict:
        raise ValueError("verification mapping required")
    required=("offline_receipt_checks_passed","transport_metadata_policy_checked",
              "status","model_promotion_allowed","production_recommendations")
    if any(key not in verification for key in required):
        raise ValueError("incomplete verification report")
    if verification["offline_receipt_checks_passed"] is not True or verification["transport_metadata_policy_checked"] is not True:
        raise ValueError("offline policy checks incomplete")
    if verification["status"]!="HOLD" or verification["model_promotion_allowed"] is not False or verification["production_recommendations"]!="DISABLED":
        raise ValueError("unsafe verification status")
    forbidden=("network_request_performed","tls_peer_authenticated",
               "checkpoint_externally_retrieved","external_checkpoint_authenticated",
               "publisher_identity_authenticated","issuer_independence_authenticated",
               "trusted_timestamp_verified")
    if any(verification.get(key) is not False for key in forbidden):
        raise ValueError("unexpected authentication claim")
    if verification.get("authenticated_samples") != 0:
        raise ValueError("unverified authenticated sample count")
    return {"evidence_class":"offline-integrity-only",
            "authenticated_samples":0,"network_origin_authenticated":False,
            "trusted_timestamp_verified":False,"status":"HOLD",
            "model_promotion_allowed":False,"production_recommendations":"DISABLED"}
