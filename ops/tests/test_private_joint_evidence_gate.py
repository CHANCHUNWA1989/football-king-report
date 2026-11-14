"""Synthetic joint evidence audits. No paid API, network, actual signatures."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_private_kickoff_crosswalk_gate import sample, source_rows, put_rows
from private_joint_evidence_gate import inspect_joint_evidence, main


def fake_signed(**changes):
    base = {
        "status": "HOLD",
        "production_recommendations": "DISABLED",
        "official_run_metadata_https_verified": True,
        "signature_and_subject_verified": True,
        "seal_witnessed_before_recorded_kickoff": True,
        "bookmaker_quote_independently_authenticated": False,
        "recorded_fixture_kickoff_independently_authenticated": False,
        "eligible_for_betting_promotion": False,
        "certified_independent_forward_samples": 0,
        "signed_seal_sha256": "c" * 64,
        "verified_rekor_timestamp_utc": "2026-11-02T05:02:00+00:00",
        "verified_github_source_sha": "a" * 40,
    }
    base.update(changes)
    return base


_MISSING = object()


def audit_case(case=None, signed=_MISSING):
    data = sample() if case is None else case
    value = fake_signed() if signed is _MISSING else signed
    with patch("private_joint_evidence_gate.audit_official_run",
               return_value=value) as called:
        result = inspect_joint_evidence(
            *data[:6], data[6][0], data[6][1], Path("/synthetic"),
            run_id="12345", attempt="1",
        )
    return result, called


class JointPrivateEvidenceGateTests(unittest.TestCase):
    def test_two_source_plus_signed_forecast_observations_only(self):
        report, official = audit_case()
        self.assertEqual(report["status"], "HOLD")
        self.assertTrue(report["private_forecast_bytes_and_seal_replayed"])
        self.assertTrue(report["two_claimed_schedule_snapshots_agreed"])
        self.assertTrue(report["official_github_signer_run_verified"])
        self.assertTrue(report["signed_seal_rekor_witness_verified"])
        self.assertTrue(report["joint_structural_checks_passed"])
        for field in (
            "schedule_snapshots_cryptographically_bound_to_signed_forecast",
            "two_source_publishers_independently_authenticated",
            "schedule_capture_clocks_independently_authenticated",
            "actual_kickoff_independently_authenticated",
            "actual_settlement_independently_authenticated",
            "executable_quote_or_positive_ev_verified",
            "eligible_for_model_scoring", "can_publish_pick",
        ):
            self.assertFalse(report[field], field)
        self.assertEqual(report["certified_independent_forward_samples"], 0)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(report["reason"], "LOCAL_TWO_SOURCE_CHECK_PLUS_SIGNED_FORECAST_ONLY")
        official.assert_called_once()
        self.assertEqual(official.call_args.kwargs["run_id"], "12345")
        safe = json.dumps(report)
        for private in ("Private Home", "Private Away", "OLDB-1", "OPEN-900",
                        "openligadb", "openfootball", "1.9183", "1.9587"):
            self.assertNotIn(private, safe)

    def test_no_signed_run_is_not_joint_verified(self):
        report, called = audit_case(signed=fake_signed(
            signature_and_subject_verified=False,
            seal_witnessed_before_recorded_kickoff=False))
        self.assertTrue(report["two_claimed_schedule_snapshots_agreed"])
        self.assertFalse(report["signed_seal_rekor_witness_verified"])
        self.assertFalse(report["joint_structural_checks_passed"])
        self.assertEqual(report["reason"], "SIGNED_SEAL_EVIDENCE_NOT_AVAILABLE")
        called.assert_called_once()

    def test_official_run_identity_missing_blocks_promotion(self):
        report, called = audit_case(signed=fake_signed(
            official_run_metadata_https_verified=False))
        self.assertFalse(report["official_github_signer_run_verified"])
        self.assertFalse(report["joint_structural_checks_passed"])
        called.assert_called_once()

    def test_crosswalk_mismatch_blocks_official_run_lookup(self):
        for mutation in ("kickoff", "team", "captured_after_prediction",
                         "wrong_source_id", "duplicate_publisher"):
            case = list(sample())
            if mutation in ("kickoff", "team"):
                rows = source_rows(case[6][1])
                rows[0]["commence_time" if mutation == "kickoff" else "home_team"] = (
                    "2026-11-02T08:00:01Z" if mutation == "kickoff" else "Different Club")
                put_rows(case[6][1], rows)
            elif mutation == "captured_after_prediction":
                case[6][1]["captured_utc"] = "2026-11-02T05:03:00Z"
            elif mutation == "wrong_source_id":
                case[6][1]["source_event_id"] = "nonexistent"
            else:
                case[6][1]["provider_namespace"] = case[6][0]["provider_namespace"]
            with self.subTest(mutation=mutation):
                result, called = audit_case(case)
                self.assertEqual(result["status"], "HOLD")
                self.assertFalse(result["joint_structural_checks_passed"])
                self.assertEqual(result["certified_independent_forward_samples"], 0)
                self.assertFalse(result["two_claimed_schedule_snapshots_agreed"])
                called.assert_not_called()

    def test_forecast_tamper_prevents_attestation_check(self):
        case = list(sample())
        case[4] += b" "
        result, called = audit_case(case)
        self.assertFalse(result["private_forecast_bytes_and_seal_replayed"])
        self.assertFalse(result["joint_structural_checks_passed"])
        called.assert_not_called()

    def test_claimed_forward_samples_or_promotion_quarantines_everything(self):
        for prop, value in (
            ("certified_independent_forward_samples", 1),
            ("eligible_for_betting_promotion", True),
            ("recorded_fixture_kickoff_independently_authenticated", True),
            ("bookmaker_quote_independently_authenticated", True),
            ("production_recommendations", "ENABLED"),
            ("status", "APPROVED"),
        ):
            with self.subTest(field=prop):
                result, _ = audit_case(signed=fake_signed(**{prop: value}))
                self.assertFalse(result["joint_structural_checks_passed"])
                self.assertFalse(result["official_github_signer_run_verified"])
                self.assertEqual(result["status"], "HOLD")
                self.assertEqual(result["certified_independent_forward_samples"], 0)

    def test_missing_signed_digest_or_timestamp_fail_closed(self):
        for key in ("signed_seal_sha256", "verified_rekor_timestamp_utc",
                    "verified_github_source_sha"):
            with self.subTest(key=key):
                bad=fake_signed()
                bad.pop(key)
                report, _ = audit_case(signed=bad)
                self.assertFalse(report["joint_structural_checks_passed"])
                self.assertFalse(report["signed_seal_rekor_witness_verified"])
                self.assertEqual(report["certified_independent_forward_samples"], 0)

    def test_identical_snapshots_fail_even_when_signed_forecast_is_true(self):
        case = list(sample())
        case[6][1]["snapshot_bytes"] = case[6][0]["snapshot_bytes"]
        case[6][1]["source_event_id"] = case[6][0]["source_event_id"]
        result, called = audit_case(case)
        self.assertFalse(result["joint_structural_checks_passed"])
        called.assert_not_called()

    def test_schedule_digest_changes_are_not_part_of_signed_forecast(self):
        case = list(sample())
        first, _ = audit_case(case)
        changed = deepcopy(case)
        rows = source_rows(changed[6][1])
        rows[0]["last_update"] = "2026-11-02T04:57:00Z"
        put_rows(changed[6][1], rows)
        second, _ = audit_case(changed)
        self.assertTrue(first["joint_structural_checks_passed"])
        self.assertTrue(second["joint_structural_checks_passed"])
        self.assertNotEqual(first["local_schedule_manifest_sha256_unanchored"],
                            second["local_schedule_manifest_sha256_unanchored"])
        self.assertFalse(first["schedule_snapshots_cryptographically_bound_to_signed_forecast"])
        self.assertFalse(second["schedule_snapshots_cryptographically_bound_to_signed_forecast"])

    def test_malformed_signer_output_is_not_a_privilege_escalation(self):
        for value in (None, [], {}, {"status":"HOLD"},
                      fake_signed(certified_independent_forward_samples=True),
                      fake_signed(signature_and_subject_verified="true"),
                      fake_signed(official_run_metadata_https_verified="yes")):
            with self.subTest(value=str(value)[:50]):
                report, _ = audit_case(signed=value)
                self.assertFalse(report["joint_structural_checks_passed"])
                self.assertFalse(report["can_publish_pick"])
                self.assertEqual(report["certified_independent_forward_samples"], 0)

    def test_local_cli_exclusive_output_0600_never_claims_authentication(self):
        raw, receipt, fixture, market, forecast, seal, sources = sample()
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            blobs = {
                "odds.json": raw,
                "receipt.json": json.dumps(receipt).encode(),
                "fixture.json": json.dumps(fixture).encode(),
                "market.json": json.dumps(market).encode(),
                "forecast.json": forecast,
                "seal.json": json.dumps(seal).encode(),
                "source-a.json": sources[0]["snapshot_bytes"],
                "source-b.json": sources[1]["snapshot_bytes"],
            }
            for filename, data in blobs.items():
                (root/filename).write_bytes(data)
            proof = root/"synthetic-proof"
            proof.mkdir()
            flags = ["--proof", str(proof)]
            for key, filename in (
                ("raw-odds", "odds.json"), ("receipt", "receipt.json"),
                ("fixture", "fixture.json"), ("market", "market.json"),
                ("forecast", "forecast.json"), ("seal", "seal.json"),
                ("source-a", "source-a.json"), ("source-b", "source-b.json"),
            ):
                flags += ["--"+key, str(root/filename)]
            for i, prefix in enumerate(("source-a", "source-b")):
                flags += ["--"+prefix+"-name", sources[i]["provider_namespace"],
                          "--"+prefix+"-id", sources[i]["source_event_id"],
                          "--"+prefix+"-captured-utc", sources[i]["captured_utc"]]
            flags += ["--run-id", "12345", "--attempt", "1",
                      "--output", str(root/"joint.json")]
            with patch("private_joint_evidence_gate.audit_official_run",
                       return_value=fake_signed()):
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(main(flags), 0, output.getvalue())
            written = json.loads((root/"joint.json").read_text())
            self.assertEqual(stat.S_IMODE((root/"joint.json").stat().st_mode), 0o600)
            self.assertTrue(written["joint_structural_checks_passed"])
            self.assertFalse(written["can_publish_pick"])
            self.assertEqual(written["certified_independent_forward_samples"], 0)
            with patch("private_joint_evidence_gate.audit_official_run",
                       return_value=fake_signed()):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(flags), 1)


if __name__ == "__main__":
    unittest.main()
