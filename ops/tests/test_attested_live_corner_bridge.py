"""Zero-network synthetic tests: mock gh output cannot prove actual signatures."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import attested_live_corner_bridge as bridge
import live_fixture_attestation_audit as witness


class AttestedLiveCornerBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.proof = Path(self.temp.name)
        self.clock = datetime(2026, 11, 4, 8, 30, tzinfo=timezone.utc)
        self.ids = {"source_sha": "1" * 40, "workflow_sha": "2" * 40,
                    "run_id": "123456789", "attempt": "1"}
        self.manifest = {
            "event_id": "fixture-A",
            "kickoff_utc": "2026-11-04T08:00:00Z",
            "registered_at_utc": "2026-11-04T07:30:00Z",
            "source_events": {
                "score": {"source": "score-test", "source_event_id": "score-A",
                          "source_url": "https://score.example.org/match/A"},
                "stats": {"source": "stats-test", "source_event_id": "stats-A",
                          "source_url": "https://stats.example.org/event/A"},
                "quote": {"source": "odds-test", "source_event_id": "odds-A",
                          "source_url": "https://odds.example.org/event/A"},
            },
        }
        self.snapshot = {
            "event_id": "fixture-A",
            "kickoff_utc": "2026-11-04T08:00:00Z",
            "decision_utc": "2050-01-01T00:00:00Z",  # deliberately fake; ignored
            "score": {
                "event_id": "fixture-A", "source": "score-test",
                "source_event_id": "score-A", "source_url": "https://score.example.org/match/A",
                "upstream_updated_utc": "2026-11-04T08:29:45Z",
                "captured_utc": "2026-11-04T08:29:50Z",
                "match_status": "FIRST_HALF", "home_goals": 0, "away_goals": 0,
                "last_material_event_utc": "2026-11-04T08:00:00Z",
            },
            "stats": {
                "event_id": "fixture-A", "source": "stats-test",
                "source_event_id": "stats-A", "source_url": "https://stats.example.org/event/A",
                "upstream_updated_utc": "2026-11-04T08:29:50Z",
                "captured_utc": "2026-11-04T08:29:53Z",
                "home_corners": 2, "away_corners": 1,
                "last_corner_event_utc": "2026-11-04T08:29:35Z",
            },
            "quote": {
                "event_id": "fixture-A", "source": "odds-test",
                "source_event_id": "odds-A", "source_url": "https://odds.example.org/event/A",
                "upstream_updated_utc": "2026-11-04T08:29:54Z",
                "captured_utc": "2026-11-04T08:29:56Z",
                "market": "corners_totals", "selection": "over", "in_play": True,
                "line": 8.5, "decimal_price": 1.90, "bookmaker": "private-test-book",
            },
        }
        self.bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
                       "dsseEnvelope": {"payload": "SYNTHETIC_NOT_CRYPTOGRAPHY"}}
        self.write_proof()

    def write_proof(self):
        (self.proof / witness.MANIFEST_NAME).write_text(
            json.dumps(self.manifest, sort_keys=True) + "\n", encoding="utf-8")
        (self.proof / witness.BUNDLE_NAME).write_text(
            json.dumps(self.bundle) + "\n", encoding="utf-8")

    def gh_stdout(self):
        digest = hashlib.sha256((self.proof / witness.MANIFEST_NAME).read_bytes()).hexdigest()
        return [{
            "attestation": {"bundle": copy.deepcopy(self.bundle)},
            "verificationResult": {
                "mediaType": "application/vnd.dev.sigstore.verificationresult+json;version=0.1",
                "signature": {"certificate": witness._certificate(
                    self.ids["source_sha"], self.ids["workflow_sha"],
                    self.ids["run_id"], self.ids["attempt"])},
                "verifiedTimestamps": [{"type": "Tlog",
                                        "uri": "https://rekor.sigstore.dev",
                                        "timestamp": "2026-11-04T07:45:00Z"}],
                "statement": {
                    "_type": "https://in-toto.io/Statement/v1",
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "subject": [{"name": witness.MANIFEST_NAME,
                                 "digest": {"sha256": digest}}],
                },
            },
        }]

    def run_bridge(self, snapshot=None, stdout=None, **override):
        payload = json.dumps(self.gh_stdout() if stdout is None else stdout).encode("utf-8")
        options = dict(self.ids, **override)
        clock = options.pop("now", self.clock)
        with patch.object(witness.subprocess, "run", return_value=
                          subprocess.CompletedProcess([], 0, payload, b"")) as gh:
            result = bridge.audit_linked(
                self.snapshot if snapshot is None else snapshot, self.proof,
                now=clock, **options,
            )
        return result, gh

    def assert_hold(self, result):
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["certified_positive_ev"])
        self.assertFalse(result["eligible_for_betting_promotion"])
        self.assertFalse(result["upstream_score_corners_quote_authenticated"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_mocked_gh_witness_plus_snapshot_is_research_only_not_certified(self):
        before = copy.deepcopy(self.snapshot)
        result, gh = self.run_bridge()
        self.assertEqual(gh.call_count, 1)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertTrue(result["manifest_sigstore_witness_verified"])
        self.assertTrue(result["same_event_live_consistency_checked"])
        self.assertFalse(result["upstream_score_corners_quote_authenticated"])
        self.assertFalse(result["certified_positive_ev"])
        self.assertFalse(result["market_executable_verified"])
        self.assertEqual(self.snapshot, before)
        self.assertNotIn("private-test-book", json.dumps(result))
        self.assertNotIn("1.9", json.dumps(result))
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_witness_failure_blocks_even_plausible_snapshot(self):
        with patch.object(witness, "audit", return_value={"status": "HOLD"}), \
             patch.object(bridge.live, "audit_live_snapshot") as live_gate:
            result = bridge.audit_linked(self.snapshot, self.proof, now=self.clock, **self.ids)
        self.assert_hold(result)
        self.assertEqual(result["reason"], "FIXTURE_MANIFEST_WITNESS_NOT_VERIFIED")
        live_gate.assert_not_called()

    def test_saved_fake_verification_report_cannot_bypass_failing_gh(self):
        (self.proof / "fake-verification.json").write_text(
            json.dumps({"status": "RESEARCH_ONLY", "verified": True}), encoding="utf-8")
        with patch.object(witness.subprocess, "run", return_value=
                          subprocess.CompletedProcess([], 1, b"", b"private-log")):
            result = bridge.audit_linked(self.snapshot, self.proof, now=self.clock, **self.ids)
        self.assert_hold(result)
        self.assertNotIn("private-log", json.dumps(result))

    def test_witness_digest_swapped_after_verification_is_hold(self):
        expected = hashlib.sha256((self.proof / witness.MANIFEST_NAME).read_bytes()).hexdigest()
        def swap_manifest(*args, **kwargs):
            changed = copy.deepcopy(self.manifest)
            changed["source_events"]["quote"]["source_event_id"] = "odds-DIFFERENT"
            (self.proof / witness.MANIFEST_NAME).write_text(
                json.dumps(changed, sort_keys=True) + "\n", encoding="utf-8")
            return {"status": "RESEARCH_ONLY", "sigstore_tlog_witness_verified": True,
                    "manifest_bytes_identity_bound": True,
                    "witness_before_recorded_kickoff": True,
                    "production_recommendations": "DISABLED",
                    "manifest_sha256": expected}
        with patch.object(witness, "audit", side_effect=swap_manifest):
            result = bridge.audit_linked(self.snapshot, self.proof, now=self.clock, **self.ids)
        self.assert_hold(result)
        self.assertEqual(result["reason"], "MANIFEST_CHANGED_AFTER_VERIFICATION")

    def test_quote_from_other_fixture_id_fails(self):
        s = copy.deepcopy(self.snapshot)
        s["quote"]["source_event_id"] = "odds-B"
        result, _ = self.run_bridge(s)
        self.assert_hold(result)
        self.assertTrue(result["manifest_sigstore_witness_verified"])
        self.assertEqual(result["reason"], "LIVE_CORNER_EVIDENCE_NOT_CONSISTENT")

    def test_quote_upstream_before_last_corner_fails(self):
        s = copy.deepcopy(self.snapshot)
        s["quote"]["upstream_updated_utc"] = "2026-11-04T08:29:34Z"
        s["quote"]["captured_utc"] = "2026-11-04T08:29:39Z"
        result, _ = self.run_bridge(s)
        self.assert_hold(result)

    def test_finished_or_abandoned_match_fails_even_with_valid_witness(self):
        for match_status in ("FINISHED", "ABANDONED", "SUSPENDED", "PENALTIES"):
            with self.subTest(match_status=match_status):
                s = copy.deepcopy(self.snapshot)
                s["score"]["match_status"] = match_status
                result, _ = self.run_bridge(s)
                self.assert_hold(result)

    def test_market_already_decided_rejected(self):
        s = copy.deepcopy(self.snapshot)
        s["stats"]["home_corners"] = 8
        result, _ = self.run_bridge(s)
        self.assert_hold(result)

    def test_noncorner_market_cannot_bypass_and_never_calls_verifier(self):
        s = copy.deepcopy(self.snapshot)
        s["quote"]["market"] = "totals"
        with patch.object(witness.subprocess, "run") as gh:
            result = bridge.audit_linked(s, self.proof, now=self.clock, **self.ids)
        self.assert_hold(result)
        self.assertEqual(result["reason"], "CORNERS_ONLY_RESEARCH_BRIDGE")
        gh.assert_not_called()

    def test_injected_future_decision_time_does_not_make_old_data_fresh(self):
        # Deliberately future self-reported timestamp; actual fixed clock is later.
        s = copy.deepcopy(self.snapshot)
        s["decision_utc"] = "2099-01-01T00:00:00Z"
        result, _ = self.run_bridge(s)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        result, _ = self.run_bridge(s, now=datetime(2026, 11, 4, 9, 0, tzinfo=timezone.utc))
        self.assert_hold(result)

    def test_gh_verifier_mismatched_certificate_fail_closed(self):
        output = self.gh_stdout()
        output[0]["verificationResult"]["signature"]["certificate"]["githubWorkflowSHA"] = "bad"
        result, _ = self.run_bridge(stdout=output)
        self.assert_hold(result)

    def test_cli_rejects_missing_and_malformed_snapshot(self):
        missing = self.proof / "missing.json"
        from contextlib import redirect_stdout
        from io import StringIO
        args = ["--snapshot", str(missing), "--proof", str(self.proof),
                "--source-sha", self.ids["source_sha"],
                "--workflow-sha", self.ids["workflow_sha"],
                "--run-id", self.ids["run_id"],
                "--attempt", self.ids["attempt"]]
        output = StringIO()
        with redirect_stdout(output):
            code = bridge.main(args)
        self.assertEqual(code, 2)
        self.assert_hold(json.loads(output.getvalue()))
        invalid = self.proof / "snapshot.json"
        invalid.write_text('{"event_id":"A","event_id":"B"}', encoding="utf-8")
        args[1] = str(invalid)
        output = StringIO()
        with redirect_stdout(output):
            code = bridge.main(args)
        self.assertEqual(code, 2)
        self.assert_hold(json.loads(output.getvalue()))


if __name__ == "__main__":
    unittest.main()
