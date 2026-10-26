"""Reverify fixed candidate bytes and compare witness with RECORDED kickoffs.

This derives observations without changing signed forecasts. Actual kickoff,
outcome independence, model calibration and production qualification remain
unverified. Saved verification JSON is never accepted as evidence.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

import forecast_provenance_audit as provenance
import model_dixon_coles_forward as producer


def _require(condition, reason):
    if not condition:
        raise provenance.AuditError(reason)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _empty_capture(capture, expected, shadow):
    """Validate registered empty metadata; never certify a missing formula."""
    _require(set(capture) == set(expected), "EMPTY_CAPTURE_SCHEMA_MISMATCH")
    variable = {"status", "source_problem", "source_as_of_utc", "predictions_count",
                "predictions", "exclusions", "maximum_original_rho0_probability_difference",
                "original_rho0_argmax_disagreements"}
    _require(_canonical({k: v for k, v in capture.items() if k not in variable}) ==
             _canonical({k: v for k, v in expected.items() if k not in variable}),
             "EMPTY_CAPTURE_REGISTERED_METADATA_MISMATCH")
    _require(capture["status"] == "HOLD" and type(capture["predictions_count"]) is int
             and capture["predictions_count"] == 0 and capture["predictions"] == []
             and capture["maximum_original_rho0_probability_difference"] is None
             and type(capture["original_rho0_argmax_disagreements"]) is int
             and capture["original_rho0_argmax_disagreements"] == 0,
             "INVALID_EMPTY_CAPTURE")
    problem = capture["source_problem"]
    _require(problem is None or (isinstance(problem, str)
             and re.fullmatch(r"[A-Z0-9_]{1,100}", problem)), "INVALID_EMPTY_CAPTURE_REASON")
    source_at = capture["source_as_of_utc"]
    _require(source_at is not None or problem is not None, "EMPTY_SOURCE_CLOCK_WITHOUT_REASON")
    if source_at is not None:
        _require(source_at == provenance._time(shadow.get("as_of_utc")).isoformat(),
                 "EMPTY_CAPTURE_SOURCE_CLOCK_MISMATCH")
    exclusions = capture["exclusions"]
    _require(isinstance(exclusions, dict) and len(exclusions) <= producer.MAX_ROWS
             and all(isinstance(k, str) and re.fullmatch(r"[A-Z0-9_]{1,100}", k)
                     and type(v) is int and 0 < v <= producer.MAX_ROWS
                     for k, v in exclusions.items())
             and sum(exclusions.values()) <= len(shadow["predictions"]),
             "INVALID_EMPTY_CAPTURE_EXCLUSIONS")


def audit(proof, *, source_sha, workflow_sha, run_id, attempt, now=None):
    report = {
        "schema": "football-king-dixon-coles-witness-audit-v1",
        "status": "HOLD", "production_recommendations": "DISABLED",
        "audit_completed": False, "candidate_capture_present": False,
        "signature_identity_and_subjects_verified": False,
        "candidate_bytes_formula_source_binding_verified": False,
        "recorded_kickoff_independently_authenticated": False,
        "outcomes_independently_authenticated": False,
        "source_identity_independently_authenticated": False,
        "model_calibration_verified": False, "prospective_qualification_verified": False,
        "market_prices_executable": False, "model_advantage_verified": False,
        "betting_roi_estimable": False, "automatic_model_promotion": False,
        "eligible_for_betting_promotion": False,
        "total_candidates": 0, "observed_before_recorded_kickoff_count": 0,
        "cases": [], "excluded_reason_counts": {},
        "notice": "只核對已簽署候選的固定公式、來源及可信見證相對記錄開波時間；不認證實際開波、賽果或正式資格。",
    }
    try:
        current = now if now is not None else datetime.now(timezone.utc)
        _require(isinstance(current, datetime) and current.tzinfo is not None
                 and current.utcoffset() is not None, "INVALID_CANDIDATE_AUDIT_CLOCK")
        current = current.astimezone(timezone.utc)
        # This invocation performs the original three genuine verifications.
        # No caller-supplied/saved report can enter this trust boundary.
        verified = provenance.audit(proof, source_sha=source_sha, workflow_sha=workflow_sha,
                                    run_id=run_id, attempt=attempt, now=current)
        _require(verified.get("audit_completed") is True
                 and verified.get("signature_identity_and_subjects_verified") is True,
                 "BASE_PROVENANCE_NOT_VERIFIED")
        report.update(source_commit=source_sha, workflow_commit=workflow_sha,
                      run_id=run_id, run_attempt=attempt, checked_utc=current.isoformat(),
                      verified_tlog_utc=verified["verified_tlog_utc"],
                      subject_sha256=verified["subject_sha256"])
        raw = provenance._read(proof / "shadow.json", provenance.MAX_FILE_BYTES)
        _require(hashlib.sha256(raw).hexdigest() == verified["subject_sha256"]["shadow.json"],
                 "SIGNED_SHADOW_CHANGED_AFTER_VERIFICATION")
        report["signature_identity_and_subjects_verified"] = True
        shadow = provenance._json(raw)
        if producer.TOP_KEY not in shadow:
            report.update(audit_completed=True, reason="NO_REGISTERED_CANDIDATE_CAPTURE")
            return report
        report["candidate_capture_present"] = True
        capture = shadow[producer.TOP_KEY]
        _require(isinstance(capture, dict), "INVALID_REGISTERED_CANDIDATE_CAPTURE")
        captured = provenance._time(capture.get("generated_utc"))
        expected = producer.build(shadow, now=captured)  # Validation only; never write a forecast.
        rows = capture.get("predictions")
        _require(isinstance(rows, list) and len(rows) <= producer.MAX_ROWS,
                 "INVALID_REGISTERED_CANDIDATE_ROWS")
        if not rows:
            _empty_capture(capture, expected, shadow)
            report.update(audit_completed=True, reason="REGISTERED_EMPTY_CAPTURE_NOT_FORMULA_EVIDENCE")
            return report
        # Type-preserving equality rejects bool/int aliases and all subset,
        # projection, formula, protocol, ordering and exclusion modifications.
        _require(_canonical(capture) == _canonical(expected), "REGISTERED_CAPTURE_RECONSTRUCTION_MISMATCH")
        witness = provenance._time(verified["verified_tlog_utc"], utc_only=True)
        _require(witness <= current + timedelta(minutes=5), "FUTURE_CANDIDATE_WITNESS")
        cases = []
        for row in rows:
            source = provenance._time(row["source_prediction_utc"])
            own = provenance._time(row["candidate_generated_utc"])
            kickoff = provenance._time(row["kickoff_utc_recorded"])
            if not source <= own <= witness:
                reason = "WITNESS_OR_CAPTURE_CHRONOLOGY_INVALID"
            elif (kickoff-own).total_seconds() <= 600 or (kickoff-witness).total_seconds() <= 600:
                reason = "WITNESS_NOT_EARLY_ENOUGH_FOR_RECORDED_KICKOFF"
            else:
                reason = "WITNESSED_BEFORE_RECORDED_KICKOFF_WITH_BUFFER"
            cases.append({
                **{k: row[k] for k in ("league", "event_id", "home", "away",
                    "kickoff_utc_recorded", "source_prediction_utc", "candidate_generated_utc",
                    "source_projection_sha256", "model_id", "protocol_sha256")},
                "verified_tlog_utc": witness.isoformat(), "reason": reason,
                "observed_before_recorded_kickoff": reason == "WITNESSED_BEFORE_RECORDED_KICKOFF_WITH_BUFFER",
                "actual_kickoff_independently_authenticated": False,
                "production_recommendations": "DISABLED",
            })
        report.update(audit_completed=True, candidate_bytes_formula_source_binding_verified=True,
                      total_candidates=len(rows), cases=cases,
                      model_id=producer.MODEL, protocol_sha256=producer.PROTOCOL_SHA256,
                      observed_before_recorded_kickoff_count=sum(
                          row["observed_before_recorded_kickoff"] for row in cases),
                      excluded_reason_counts=dict(Counter(row["reason"] for row in cases
                          if not row["observed_before_recorded_kickoff"])),
                      reason="RECORDED_CANDIDATE_WITNESS_AUDIT_COMPLETED")
    except (provenance.AuditError, OSError, ValueError, TypeError, OverflowError,
            RecursionError, KeyError, AttributeError) as exc:
        report.update(audit_completed=False,
                      candidate_bytes_formula_source_binding_verified=False,
                      total_candidates=0, observed_before_recorded_kickoff_count=0, cases=[],
                      excluded_reason_counts={},
                      reason=str(exc) if isinstance(exc, provenance.AuditError) else "CANDIDATE_AUDIT_INPUT_OR_TOOL_ERROR")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    protected = [args.proof/name for name in provenance.SUBJECT_NAMES + ("research.sigstore.json",)]
    aliases = args.output.exists() and any(p.exists() and args.output.samefile(p) for p in protected)
    if args.output.is_symlink() or args.output.resolve().is_relative_to(args.proof.resolve()) or aliases:
        parser.error("--output must be separate from the signed proof")
    report = audit(args.proof, source_sha=args.source_sha, workflow_sha=args.workflow_sha,
                   run_id=args.run_id, attempt=args.attempt)
    try:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    except OSError:
        return 1
    return 0 if report["audit_completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
