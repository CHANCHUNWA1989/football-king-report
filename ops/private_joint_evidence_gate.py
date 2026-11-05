"""Fail-closed joint audit: pre-match private forecast + two schedules + Sigstore.

This is an OBSERVATION ONLY gate, not a license to wager. A GitHub-signed
forecast digest cannot attest the separately submitted schedule snapshots;
their claimed names/clocks are still unauthenticated. Each gate must verify
the same raw odds, receipt, forecast bytes, seal and fixture/line. A successful
structural match does not prove real market executability or actual kickoff.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

from private_kickoff_crosswalk_gate import (
    CrosswalkError, crosscheck,
)
from private_quote_official_run_gate import (
    audit_official_run, OfficialRunError, MAX_RAW_ODDS_BYTES, MAX_LOCAL_BYTES,
)
from private_quote_seal_attestation import (
    AttestationError, _read,
)
from private_quote_forward_freeze import FreezeError, _json_bytes_object
from private_schedule_snapshot_commitment import CommitmentError, replay_commitment
from private_quote_snapshot_receipt import (
    ReceiptError, _payload_receipt, _write_private_new,
)

SCHEMA = "football-king-private-joint-prospective-evidence-audit-v1"
REQUIRED_CROSSWALK_TRUE = (
    "private_forecast_seal_replayed",
    "two_distinct_claimed_publisher_namespaces",
    "two_nonidentical_local_schedule_snapshots",
    "both_schedule_event_ids_unique_in_their_snapshots",
    "home_and_away_orientation_exactly_matched",
    "kickoff_instant_exactly_agreed",
    "both_observations_claimed_available_before_prediction",
)
REQUIRED_CROSSWALK_FALSE = (
    "source_raw_payloads_independently_authenticated",
    "publisher_independence_independently_verified",
    "schedule_captured_clocks_independently_attested",
    "source_fixture_id_crosswalk_independently_authenticated",
    "actual_kickoff_independently_confirmed",
    "eligible_for_model_scoring",
    "eligible_for_betting_promotion",
)
REQUIRED_RUN_FALSE = (
    "bookmaker_quote_independently_authenticated",
    "recorded_fixture_kickoff_independently_authenticated",
    "eligible_for_betting_promotion",
)


def _base():
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "private_forecast_bytes_and_seal_replayed": False,
        "two_claimed_schedule_snapshots_agreed": False,
        "official_github_signer_run_verified": False,
        "signed_seal_rekor_witness_verified": False,
        "joint_structural_checks_passed": False,
        "local_schedule_commitment_replayed": False,
        "schedule_commitment_externally_witnessed": False,
        "schedule_snapshots_cryptographically_bound_to_signed_forecast": False,
        "two_source_publishers_independently_authenticated": False,
        "schedule_capture_clocks_independently_authenticated": False,
        "actual_kickoff_independently_authenticated": False,
        "executable_quote_or_positive_ev_verified": False,
        "actual_settlement_independently_authenticated": False,
        "certified_independent_forward_samples": 0,
        "eligible_for_model_scoring": False,
        "can_publish_pick": False,
    }


def inspect_joint_evidence(
        raw_odds, receipt, fixture, market, forecast_raw, seal,
        source_a, source_b, proof, *, run_id, attempt, now=None,
        schedule_commitment=None, seal_raw=None):
    """Recheck all local input data, then independently verify official run.

    All inputs are PRIVATE. No API usage except a read-only official GitHub
    run lookup and the existing verifier's Sigstore certificate lookup.
    """
    report = _base()
    try:
        structural = crosscheck(raw_odds, receipt, fixture, market,
                                forecast_raw, seal, [source_a, source_b])
        if (structural.get("status") != "RESEARCH_ONLY"
                or structural.get("production_recommendations") != "DISABLED"
                or type(structural.get("certified_independent_forward_samples")) is not int
                or structural["certified_independent_forward_samples"] != 0
                or not all(structural.get(k) is True for k in REQUIRED_CROSSWALK_TRUE)
                or not all(structural.get(k) is False for k in REQUIRED_CROSSWALK_FALSE)):
            raise CrosswalkError("UNSAFE_SCHEDULE_CROSSWALK_CLAIMS")
        report["private_forecast_bytes_and_seal_replayed"] = True
        report["two_claimed_schedule_snapshots_agreed"] = True
        # A local hash of both claimed snapshots is useful to detect a later
        # swap in a private audit log, but it is NOT sealed or independently
        # timestamped. No private team IDs, names, odds or source bodies output.
        source_bytes = [
            hashlib.sha256(source["snapshot_bytes"]).hexdigest()
            for source in (source_a, source_b)
        ]
        if len(set(source_bytes)) != 2:
            raise CrosswalkError("IDENTICAL_SCHEDULE_BYTES")
        local_manifest = {
            "forecast_seal_checksum_unanchored": seal["seal_sha256_unanchored"],
            "claimed_schedule_snapshot_sha256_sorted": sorted(source_bytes),
        }
        manifest_raw = json.dumps(local_manifest, separators=(",", ":"),
                                  sort_keys=True).encode("ascii")
        report["local_schedule_manifest_sha256_unanchored"] = hashlib.sha256(
            manifest_raw).hexdigest()

        if (schedule_commitment is None) != (seal_raw is None):
            raise CommitmentError("MISSING_SCHEDULE_COMMITMENT_BYTES")
        if schedule_commitment is not None:
            replay = replay_commitment(
                raw_odds, receipt, fixture, market, forecast_raw,
                seal_raw, [source_a, source_b], schedule_commitment,
            )
            if (replay.get("local_schedule_manifest_bytes_and_semantics_replayed") is not True
                    or replay.get("schedule_bytes_externally_attested") is not False
                    or type(replay.get("certified_independent_forward_samples")) is not int
                    or replay["certified_independent_forward_samples"] != 0):
                raise CommitmentError("UNSAFE_SCHEDULE_COMMITMENT_REPLAY")
            report["local_schedule_commitment_replayed"] = True
            report["local_schedule_commitment_sha256_unanchored"] = (
                replay["local_manifest_sha256_unanchored"])

        signed = audit_official_run(
            proof, raw_odds, receipt, fixture, market, forecast_raw,
            run_id=run_id, attempt=attempt, now=now,
        )
        if (type(signed) is not dict
                or signed.get("status") != "HOLD"
                or signed.get("production_recommendations") != "DISABLED"
                or type(signed.get("certified_independent_forward_samples")) is not int
                or signed["certified_independent_forward_samples"] != 0
                or not all(signed.get(k) is False for k in REQUIRED_RUN_FALSE)):
            raise ValueError("UNSAFE_SIGNED_RUN_CLAIMS")
        report["official_github_signer_run_verified"] = (
            signed.get("official_run_metadata_https_verified") is True)
        if (signed.get("signature_and_subject_verified") is not True
                or signed.get("seal_witnessed_before_recorded_kickoff") is not True
                or report["official_github_signer_run_verified"] is not True):
            report["reason"] = "SIGNED_SEAL_EVIDENCE_NOT_AVAILABLE"
            return report
        if (type(signed.get("signed_seal_sha256")) is not str
                or type(signed.get("verified_rekor_timestamp_utc")) is not str
                or type(signed.get("verified_github_source_sha")) is not str):
            raise ValueError("MISSING_SIGNED_RUN_BINDING")
        report["signed_seal_rekor_witness_verified"] = True
        report["joint_structural_checks_passed"] = True
        # Even a genuine Rekor witness binds ONLY the signed forecast seal
        # bytes. Two after-the-fact, merely caller-timestamped schedules
        # cannot become independently witnessed pre-match data by association.
        report["reason"] = "LOCAL_TWO_SOURCE_CHECK_PLUS_SIGNED_FORECAST_ONLY"
    except (CrosswalkError, CommitmentError, FreezeError, ReceiptError, OfficialRunError,
            AttestationError, ValueError, TypeError, KeyError, OSError,
            OverflowError, RecursionError) as exc:
        # Prevent optimistic booleans escaping after mid-chain errors.
        report = _base()
        report["reason"] = (
            str(exc) if isinstance(exc, CrosswalkError)
            else "INCOMPLETE_OR_UNSAFE_JOINT_EVIDENCE")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-odds", "receipt", "fixture", "market", "forecast", "seal",
                 "source-a", "source-b", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--proof", type=Path, required=True)
    parser.add_argument("--schedule-commitment", type=Path)
    for name in ("source-a-name", "source-a-id", "source-a-captured-utc",
                 "source-b-name", "source-b-id", "source-b-captured-utc",
                 "run-id", "attempt"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = _payload_receipt(_read(args.receipt, MAX_LOCAL_BYTES))
        fixture = _json_bytes_object(_read(args.fixture, MAX_LOCAL_BYTES))
        market = _json_bytes_object(_read(args.market, MAX_LOCAL_BYTES))
        seal_raw = _read(args.seal, MAX_LOCAL_BYTES)
        seal = _json_bytes_object(seal_raw)
        schedule_commitment = (_json_bytes_object(_read(args.schedule_commitment, MAX_LOCAL_BYTES))
                               if args.schedule_commitment is not None else None)
        source_a = {
            "provider_namespace": args.source_a_name,
            "source_event_id": args.source_a_id,
            "captured_utc": args.source_a_captured_utc,
            "snapshot_bytes": _read(args.source_a, 1_000_000),
        }
        source_b = {
            "provider_namespace": args.source_b_name,
            "source_event_id": args.source_b_id,
            "captured_utc": args.source_b_captured_utc,
            "snapshot_bytes": _read(args.source_b, 1_000_000),
        }
        report = inspect_joint_evidence(
            _read(args.raw_odds, MAX_RAW_ODDS_BYTES), receipt,
            fixture, market, _read(args.forecast, MAX_LOCAL_BYTES),
            seal, source_a, source_b, args.proof,
            run_id=args.run_id, attempt=args.attempt,
            schedule_commitment=schedule_commitment,
            seal_raw=seal_raw if schedule_commitment is not None else None,
        )
        _write_private_new(args.output, report)
    except (ReceiptError, CrosswalkError, CommitmentError, FreezeError,
            AttestationError, OSError, ValueError, TypeError,
            OverflowError) as exc:
        print(json.dumps({"status": "HOLD", "reason": "INVALID_PRIVATE_INPUT",
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({
        "status": "HOLD", "joint_structural_checks_passed":
        report["joint_structural_checks_passed"],
        "certified_independent_forward_samples": 0,
        "production_recommendations": "DISABLED",
    }))
    return 0 if report["joint_structural_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
