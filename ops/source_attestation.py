"""Offline source-attestation review gate. Never auto-certifies betting edge."""
from datetime import datetime
from urllib.parse import urlparse
from ops.snapshot_validation import validate_dataset

PRODUCTION_RECOMMENDATIONS = "DISABLED"

def review_source_attestation(records, attestations):
    """Return auditable reasons, never a positive-EV approval.

    Attestations must be provided by a human reviewer after checking provider
    licensing, actual source URLs and independent forecast provenance.
    """
    rows = validate_dataset(records)
    if not isinstance(attestations, dict):
        raise ValueError("attestations must be a mapping")
    required = ("provider_name", "license_reference", "reviewer", "reviewed_at",
                "source_domain", "data_access_scope", "forecast_lineage_reference")
    missing = [key for key in required if not isinstance(attestations.get(key), str) or not attestations[key].strip()]
    reasons = []
    if missing:
        reasons.append("missing attestation fields: " + ", ".join(missing))
    domain = attestations.get("source_domain", "")
    if domain:
        for row in rows:
            host = urlparse(row["source_url"]).hostname
            if host != domain:
                reasons.append("source domain mismatch")
                break
    if attestations.get("reviewed_at"):
        try:
            stamp = datetime.fromisoformat(attestations["reviewed_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValueError("timezone required")
        except ValueError:
            reasons.append("invalid review timestamp")
    return {
        "snapshot_count": len(rows),
        "attestation_fields_complete": not reasons,
        "review_flags": reasons,
        "external_evidence_independently_verified": False,
        "provider_license_independently_verified": False,
        "forecast_lineage_independently_verified": False,
        "out_of_sample_verified": False,
        "positive_ev_verified": False,
        "production_recommendation_allowed": False,
        "decision": "HOLD",
    }
