"""Phase 10 release gate: never equate CI success with production readiness."""
import hashlib
import json


REQUIRED_CI = (
    "Football pinned walk-forward research tests",
    "Unified prediction ledger tests",
    "Football offline 1X2 validation",
    "Football King Regression and Failover CI",
    "足球王者｜安全回歸測試",
    "Repository Safety Check",
)


def evaluate_release(*, commit_sha, ci_conclusions, sandbox_evidence=None,
                     tsa_evidence=None, source_evidence=None,
                     heldout_evidence=None):
    reasons = []
    if not isinstance(commit_sha, str) or len(commit_sha) != 40 or any(
            ch not in "0123456789abcdef" for ch in commit_sha):
        reasons.append("UNPINNED_COMMIT")
    if not isinstance(ci_conclusions, dict):
        ci_conclusions = {}
    for name in REQUIRED_CI:
        if ci_conclusions.get(name) != "success":
            reasons.append("CI_NOT_SUCCESS:" + name)
    # These must be checked by independent validators in a later stage.
    # Never treat caller-provided boolean flags as proof of provenance.
    reasons.extend((
        "REAL_SANDBOX_ATTESTATION_MISSING",
        "INDEPENDENT_TSA_ATTESTATION_MISSING",
        "INDEPENDENT_PROVIDER_TRUST_MISSING",
        "HELDOUT_VALIDATION_ATTESTATION_MISSING",
    ))
    record = {"commit_sha": commit_sha, "ci": {
        name: ci_conclusions.get(name, "missing") for name in REQUIRED_CI},
        "rejection_reasons": reasons, "status": "HOLD",
        "production_recommendations": "DISABLED"}
    record["manifest_sha256"] = hashlib.sha256(json.dumps(
        record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return record
