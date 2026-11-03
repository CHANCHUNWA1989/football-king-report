"""Fail-closed opt-in research bridge: verified manifest witness -> live corner gate.

This bridge performs a FRESH verifier call through live_fixture_attestation_audit.
It never treats submitted witness reports, manifest registration times, GH
commit dates, raw odds, or snapshot fields as source authentication.

Even RESEARCH_ONLY does not authenticate live feeds, actual kickoff, bookmaker
execution, probabilities or positive EV. It never touches production gates.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import live_fixture_attestation_audit as witness
import live_quote_snapshot_guard as live

MAX_SNAPSHOT_BYTES = 512_000


def _hold(reason, *, verified_manifest=False):
    return {
        "schema": "football-king-attested-live-corner-bridge-v1",
        "status": "HOLD",
        "reason": reason,
        "manifest_sigstore_witness_verified": verified_manifest,
        "same_event_live_consistency_checked": False,
        "recorded_kickoff_independently_authenticated": False,
        "upstream_score_corners_quote_authenticated": False,
        "market_executable_verified": False,
        "probability_calibrated": False,
        "certified_positive_ev": False,
        "eligible_for_model_scoring": False,
        "eligible_for_betting_promotion": False,
        "production_recommendations": "DISABLED",
    }


def audit_linked(snapshot, proof, *, source_sha, workflow_sha, run_id, attempt, now=None):
    """Require an actual attestation recheck before joining source-map to quote.

    For tests, now may be a fixed aware datetime. CLI always uses its own UTC
    clock, never the snapshot's user-supplied decision time.
    """
    try:
        if type(snapshot) is not dict or type(snapshot.get("quote")) is not dict:
            return _hold("INVALID_LIVE_SNAPSHOT")
        if snapshot["quote"].get("market") != "corners_totals":
            return _hold("CORNERS_ONLY_RESEARCH_BRIDGE")
        clock = datetime.now(timezone.utc) if now is None else now
        if (not isinstance(clock, datetime) or clock.tzinfo is None
                or clock.utcoffset() is None):
            return _hold("INVALID_DECISION_CLOCK")
        clock = clock.astimezone(timezone.utc)
        verification = witness.audit(
            proof, source_sha=source_sha, workflow_sha=workflow_sha,
            run_id=run_id, attempt=attempt, now=clock,
        )
        if (verification.get("status") != "RESEARCH_ONLY"
                or verification.get("sigstore_tlog_witness_verified") is not True
                or verification.get("manifest_bytes_identity_bound") is not True
                or verification.get("witness_before_recorded_kickoff") is not True
                or verification.get("production_recommendations") != "DISABLED"):
            return _hold("FIXTURE_MANIFEST_WITNESS_NOT_VERIFIED")
        # The verification routine reads original bytes before invoking gh.
        # Re-read them and reject any post-verification byte swap. Never trust
        # a saved JSON verdict claiming that a different file was verified.
        raw = witness._read(proof, witness.MANIFEST_NAME, witness.MAX_MANIFEST_BYTES)
        sha256 = hashlib.sha256(raw).hexdigest()
        if sha256 != verification.get("manifest_sha256"):
            return _hold("MANIFEST_CHANGED_AFTER_VERIFICATION")
        manifest = witness._parse_json(raw)
        witness.validate_manifest(manifest)
        checked = dict(snapshot)
        checked["decision_utc"] = clock.isoformat()
        live_result = live.audit_live_snapshot(checked, trusted_fixture=manifest)
        if (live_result.get("status") != "RESEARCH_ONLY"
                or live_result.get("production_recommendations") != "DISABLED"
                or live_result.get("certified_positive_ev") is not False):
            return _hold("LIVE_CORNER_EVIDENCE_NOT_CONSISTENT",
                         verified_manifest=True)
        return {
            **_hold("WITNESSED_MANIFEST_AND_UNAUTHENTICATED_LIVE_INPUT_CONSISTENT",
                    verified_manifest=True),
            "status": "RESEARCH_ONLY",
            "same_event_live_consistency_checked": True,
        }
    except (witness.WitnessError, OSError, TypeError, ValueError, KeyError,
            OverflowError, AttributeError, RecursionError):
        return _hold("ATTESTED_LIVE_BRIDGE_INPUT_OR_TOOL_ERROR")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", required=True)
    args = parser.parse_args(argv)
    try:
        if args.snapshot.is_symlink() or not args.snapshot.is_file():
            raise ValueError("UNSAFE_SNAPSHOT_FILE")
        with args.snapshot.open("rb") as stream:
            raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if not raw or len(raw) > MAX_SNAPSHOT_BYTES:
            raise ValueError("INVALID_SNAPSHOT_SIZE")
        snapshot = witness._parse_json(raw)
        result = audit_linked(
            snapshot, args.proof, source_sha=args.source_sha,
            workflow_sha=args.workflow_sha, run_id=args.run_id,
            attempt=args.attempt,
        )
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        result = _hold("INVALID_SNAPSHOT_FILE_OR_FORMAT")
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "RESEARCH_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
