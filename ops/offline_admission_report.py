"""Machine-readable audit of pinned historical walk-forward admission.

This is a diagnostic report, not an external timestamp attestation.
"""
from offline_pinned_walkforward import replay_pinned_walkforward
from offline_source_receipt import validate_source_receipt
from offline_signed_receipt import verify_signed_source_receipt
from offline_trusted_key_registry import load_trusted_key_registry
from offline_timestamp_evidence import validate_timestamp_evidence
from offline_timestamp_attestation import inspect_timestamp_attestation


def build_pinned_admission_report(path, *, expected_sha256, expected_model_version,
                                  manifest_path, expected_manifest_sha256,
                                  min_train=60, test_size=30, step_size=30,
                                  embargo_hours=24, source_receipt=None,
                                  trusted_key_id=None, trusted_registry_path=None,
                                  trusted_registry_sha256=None,
                                  timestamp_evidence_path=None,
                                  timestamp_evidence_sha256=None,
                                  timestamp_attestation_path=None,
                                  timestamp_attestation_sha256=None):
    result = replay_pinned_walkforward(
        path, expected_sha256=expected_sha256,
        expected_model_version=expected_model_version,
        manifest_path=manifest_path,
        expected_manifest_sha256=expected_manifest_sha256,
        min_train=min_train, test_size=test_size,
        step_size=step_size, embargo_hours=embargo_hours)
    admitted = result["status"] == "RESEARCH_ONLY"
    receipt = validate_source_receipt(
        source_receipt.get("receipt") if isinstance(source_receipt, dict) else None,
        expected_history_sha256=expected_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_model_version=expected_model_version)
    receipt_ok = receipt["status"] == "RESEARCH_ONLY"
    registry = load_trusted_key_registry(
        trusted_registry_path, expected_sha256=trusted_registry_sha256,
        key_id=trusted_key_id)
    registry_ok = registry["status"] == "RESEARCH_ONLY"
    signature = verify_signed_source_receipt(
        source_receipt, trusted_key_id=trusted_key_id,
        trusted_public_key_b64=registry.get("public_key_b64"),
        expected_history_sha256=expected_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_model_version=expected_model_version)
    signature_ok = signature["signature_verified"] is True
    timestamp = validate_timestamp_evidence(
        timestamp_evidence_path, expected_sha256=timestamp_evidence_sha256,
        expected_history_sha256=expected_sha256,
        expected_manifest_sha256=expected_manifest_sha256)
    timestamp_ok = timestamp["status"] == "RESEARCH_ONLY"
    attestation = inspect_timestamp_attestation(
        timestamp_attestation_path,
        expected_sha256=timestamp_attestation_sha256,
        expected_evidence_sha256=timestamp_evidence_sha256)
    attestation_ok = attestation["status"] == "RESEARCH_ONLY"
    if not receipt_ok or not registry_ok or not signature_ok or not timestamp_ok or not attestation_ok:
        admitted = False
    history_ok = result["status"] == "RESEARCH_ONLY"
    # Consistency is not independent authentication; never grant production access.
    checks = {
        "history_digest_and_schema": "PASS" if history_ok or "preflight_reason" in result or "evidence_reason" in result or "evaluation_reason" in result else "FAIL",
        "forecast_rows": "PASS" if history_ok or "evidence_reason" in result or "evaluation_reason" in result else "NOT_RUN",
        "capture_manifest": "PASS" if history_ok or "evaluation_reason" in result else "NOT_VERIFIED",
        "walkforward": "PASS" if history_ok else "NOT_ADMITTED",
        "trusted_timestamp_authority": "NOT_VERIFIED",
        "timestamp_evidence_integrity": "PASS" if timestamp_ok else "FAIL",
        "timestamp_attestation_integrity": "PASS" if attestation_ok else "FAIL",
        "source_authenticity": "NOT_VERIFIED",
        "real_world_positive_ev": "NOT_VERIFIED",
        "source_receipt_consistency": "PASS" if receipt_ok else "FAIL",
        "issuer_identity": "NOT_VERIFIED",
        "receipt_signature": "PASS" if signature_ok else "FAIL",
        "trusted_key_registry": "PASS" if registry_ok else "FAIL",
        "production_admission": "BLOCKED",
    }
    return {
        "status": "RESEARCH_ONLY" if admitted else "HOLD",
        "reason": ("INVALID_TIMESTAMP_ATTESTATION" if not attestation_ok
                   else "INVALID_TIMESTAMP_EVIDENCE" if not timestamp_ok
                   else "UNTRUSTED_KEY_REGISTRY" if not registry_ok
                   else "UNVERIFIED_RECEIPT_SIGNATURE" if not signature_ok
                   else "INVALID_EXTERNAL_SOURCE_RECEIPT" if not receipt_ok
                   else result["reason"]),
        "checks": checks,
        "history_sha256": result.get("source_sha256"),
        "model_version": result.get("source_model_version"),
        "history_row_count": result.get("source_row_count"),
        "manifest_sha256": result.get("capture_manifest_sha256"),
        "capture_event_count": result.get("capture_event_count"),
        "fold_count": result.get("fold_count"),
        "mean_fold_brier": result.get("mean_fold_brier"),
        "failure": {**{key: value for key, value in result.items()
                    if key.endswith("_reason")},
                    **({} if receipt_ok else {"receipt_reason": receipt["reason"]}),
                    **({} if signature_ok else {"signature_reason": signature["reason"]}),
                    **({} if registry_ok else {"registry_reason": registry["reason"]}),
                    **({} if timestamp_ok else {"timestamp_reason": timestamp["reason"]}),
                    **({} if attestation_ok else {"attestation_reason": attestation["reason"]})},
        "production_recommendations": "DISABLED",
    }
