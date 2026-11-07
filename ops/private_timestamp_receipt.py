"""Verify an externally supplied snapshot timestamp receipt without self-attestation.

A receipt alone is not evidence: the trusted digest/time must come from an
independent, separately authenticated transport or configured trust anchor.
"""
from datetime import datetime, timezone
from ops.private_forecast_snapshot import verify


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_ATTESTATION_TIME")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_ATTESTATION_TIME") from exc
    if stamp.tzinfo is None:
        raise ValueError("NAIVE_ATTESTATION_TIME")
    return stamp.astimezone(timezone.utc)


def check(snapshot, receipt, *, trusted_digest=None, trusted_timestamp=None):
    verify(snapshot)
    if not isinstance(receipt, dict) or set(receipt) != {"sha256", "timestamp_utc", "authority"}:
        raise ValueError("INVALID_ATTESTATION_RECEIPT")
    if not isinstance(receipt["authority"], str) or not receipt["authority"] or len(receipt["authority"]) > 128:
        raise ValueError("INVALID_ATTESTATION_AUTHORITY")
    if receipt["sha256"] != snapshot["sha256"]:
        raise ValueError("ATTESTATION_DIGEST_MISMATCH")
    stamp = _time(receipt["timestamp_utc"])
    kickoff = _time(snapshot["forecast"]["kickoff_utc"])
    if stamp >= kickoff:
        raise ValueError("ATTESTATION_NOT_PREMATCH")
    # No trusted external channel supplied: report unverified, never promote.
    authenticated = (isinstance(trusted_digest, str) and
                     trusted_digest == receipt["sha256"] and
                     isinstance(trusted_timestamp, str) and
                     _time(trusted_timestamp) == stamp)
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "sha256": snapshot["sha256"], "receipt_consistent": True,
            "trusted_reference_matched": authenticated,
            "independent_authority_authenticated": False,
            "capture_time_independently_attested": False,
            "positive_ev_verified": False}
