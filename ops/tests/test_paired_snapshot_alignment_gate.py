"""Synthetic adversarial tests. None authenticates a real football fixture."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from ops.paired_snapshot_alignment_gate import audit_aligned

BASE = datetime(2026, 11, 8, 20, tzinfo=timezone.utc)
IDENTITY = ("source_namespace", "fixture_id", "league_id",
            "home_team_id", "away_team_id", "kickoff_utc", "as_of_utc")


def _utc(value):
    return value.isoformat().replace("+00:00", "Z")


def sample(count=2):
    fixtures = []
    a, challenger, market = [], [], []
    for i in range(count):
        kickoff = BASE + timedelta(days=i)
        cutoff = kickoff - timedelta(hours=1)
        fixture = {
            "source_namespace": "synthetic-league",
            "fixture_id": "match-" + str(i),
            "league_id": "league-1",
            "home_team_id": "team-" + str(i * 2),
            "away_team_id": "team-" + str(i * 2 + 1),
            "kickoff_utc": _utc(kickoff), "as_of_utc": _utc(cutoff),
            "result_received_utc": _utc(kickoff + timedelta(hours=2)),
            "outcome": i % 3,
        }
        shared = {k: fixture[k] for k in IDENTITY}
        fixtures.append(fixture)
        a.append({
            **shared, "produced_utc": _utc(cutoff - timedelta(minutes=15)),
            "max_input_received_utc": _utc(cutoff - timedelta(minutes=45)),
            "probabilities": [0.5, 0.3, 0.2],
        })
        challenger.append({
            **shared, "produced_utc": _utc(cutoff - timedelta(minutes=10)),
            "max_input_received_utc": _utc(cutoff - timedelta(minutes=40)),
            "probabilities": [0.6, 0.25, 0.15],
        })
        market.append({
            **shared, "quote_received_utc": _utc(cutoff - timedelta(minutes=20)),
            "bookmaker_id": "synthetic-quote-provider",
            "market_type": "1X2",
            "probabilities": [0.48, 0.30, 0.22],
        })
    return {
        "schema": "football-king-paired-snapshot-alignment-v1",
        "production_recommendations": "DISABLED",
        "fixtures": fixtures, "model_a": a,
        "challenger": challenger, "market": market,
    }


class StrictSnapshotAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.data = sample()

    def check(self):
        return audit_aligned(self.data)

    def test_valid_internal_pair_is_hold_and_diagnostic_only(self):
        result = self.check()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"],
                         "ALIGNED_TRANSCRIPTIONS_ONLY_EXTERNAL_ATTESTATION_MISSING")
        self.assertEqual(result["paired_fixture_count"], 2)
        self.assertTrue(result["per_fixture_native_identity_checked"])
        self.assertTrue(result["shared_cutoff_consistent_by_claim"])
        self.assertTrue(result["quote_precedes_both_model_snapshots_by_claim"])
        for name in ("model_a", "challenger", "market"):
            self.assertIn("log_loss", result["unverified_diagnostic_metrics"][name])
        for field in ("positive_ev_verified", "model_promoted",
                      "eligible_for_model_scoring", "independent_provenance_verified",
                      "independent_score_verified", "trusted_forecast_timestamp_verified",
                      "trusted_market_quote_verified"):
            self.assertFalse(result[field])
        self.assertEqual(result["certified_prospective_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_order_independent_join_by_native_identity(self):
        self.data["challenger"].reverse()
        self.data["market"].reverse()
        self.assertEqual(self.check()["paired_fixture_count"], 2)

    def test_missing_market_blocks_entire_cohort(self):
        self.data["market"].pop()
        result = self.check()
        self.assertEqual(result["reason"], "INCOMPLETE_PAIRED_COHORT")
        self.assertNotIn("unverified_diagnostic_metrics", result)

    def test_missing_challenger_blocks_entire_cohort(self):
        self.data["challenger"].pop()
        self.assertEqual(self.check()["reason"], "INCOMPLETE_PAIRED_COHORT")

    def test_duplicate_model_fixture_blocks(self):
        self.data["model_a"][1] = copy.deepcopy(self.data["model_a"][0])
        self.assertEqual(self.check()["reason"], "DUPLICATE_OR_UNKNOWN_FIXTURE")

    def test_cross_source_same_id_is_not_canonical_match(self):
        self.data["model_a"][0]["source_namespace"] = "other-league"
        self.assertEqual(self.check()["reason"], "DUPLICATE_OR_UNKNOWN_FIXTURE")

    def test_wrong_home_team_rejected(self):
        self.data["challenger"][0]["home_team_id"] = "team-999"
        self.assertEqual(self.check()["reason"], "FIXTURE_IDENTITY_MISMATCH")

    def test_swapped_home_away_rejected(self):
        row = self.data["market"][0]
        row["home_team_id"], row["away_team_id"] = row["away_team_id"], row["home_team_id"]
        self.assertEqual(self.check()["reason"], "FIXTURE_IDENTITY_MISMATCH")

    def test_wrong_kickoff_rejected(self):
        self.data["model_a"][0]["kickoff_utc"] = "2026-11-08T21:00:00Z"
        self.assertEqual(self.check()["reason"], "KICKOFF_MISMATCH")

    def test_model_cutoff_mismatch_rejected(self):
        self.data["challenger"][0]["as_of_utc"] = "2026-11-08T18:59:00Z"
        self.assertEqual(self.check()["reason"], "CUTOFF_MISMATCH")

    def test_market_cutoff_mismatch_rejected(self):
        self.data["market"][1]["as_of_utc"] = "2026-11-09T18:30:00Z"
        self.assertEqual(self.check()["reason"], "CUTOFF_MISMATCH")

    def test_equivalent_timezone_offset_is_allowed(self):
        self.data["model_a"][0]["as_of_utc"] = "2026-11-09T03:00:00+08:00"
        self.assertEqual(self.check()["paired_fixture_count"], 2)

    def test_naive_timestamp_rejected(self):
        self.data["model_a"][0]["produced_utc"] = "2026-11-08T18:45:00"
        self.assertEqual(self.check()["reason"], "INVALID_TIMESTAMP")

    def test_model_produced_after_cutoff_rejected(self):
        self.data["model_a"][0]["produced_utc"] = "2026-11-08T19:01:00Z"
        self.assertEqual(self.check()["reason"], "MODEL_SNAPSHOT_OR_INPUT_LOOKAHEAD")

    def test_model_input_received_after_produced_rejected(self):
        self.data["challenger"][0]["max_input_received_utc"] = "2026-11-08T18:59:00Z"
        self.assertEqual(self.check()["reason"], "MODEL_SNAPSHOT_OR_INPUT_LOOKAHEAD")

    def test_model_stale_rejected(self):
        self.data["model_a"][0]["produced_utc"] = "2026-11-08T16:00:00Z"
        self.data["model_a"][0]["max_input_received_utc"] = "2026-11-08T15:30:00Z"
        self.assertEqual(self.check()["reason"], "STALE_MODEL_SNAPSHOT")

    def test_market_quote_after_cutoff_rejected(self):
        self.data["market"][0]["quote_received_utc"] = "2026-11-08T19:01:00Z"
        self.assertEqual(self.check()["reason"], "MARKET_TIME_INVALID")

    def test_market_quote_after_first_model_snapshot_rejected(self):
        self.data["market"][0]["quote_received_utc"] = "2026-11-08T18:48:00Z"
        self.assertEqual(self.check()["reason"], "MARKET_AFTER_MODEL_SNAPSHOT")

    def test_stale_market_quote_rejected(self):
        self.data["market"][0]["quote_received_utc"] = "2026-11-08T15:00:00Z"
        self.assertEqual(self.check()["reason"], "STALE_MARKET_SNAPSHOT")

    def test_non_1x2_market_rejected(self):
        self.data["market"][0]["market_type"] = "asian_handicap"
        self.assertEqual(self.check()["reason"], "UNSUPPORTED_MARKET")

    def test_cannot_add_fake_source_certification(self):
        self.data["market"][0]["independently_verified"] = True
        self.assertEqual(self.check()["reason"], "INVALID_PAIRED_STREAM_SCHEMA")

    def test_cannot_enable_production(self):
        self.data["production_recommendations"] = "ENABLED"
        self.assertEqual(self.check()["reason"], "INVALID_ALIGNMENT_CONTRACT")

    def test_boolean_goal_outcome_rejected(self):
        self.data["fixtures"][0]["outcome"] = True
        self.assertEqual(self.check()["reason"], "INVALID_OUTCOME")

    def test_boolean_probability_rejected(self):
        self.data["challenger"][0]["probabilities"] = [True, 0., 0.]
        self.assertEqual(self.check()["reason"], "INVALID_PROBABILITIES")

    def test_nonfinite_probability_rejected(self):
        self.data["model_a"][0]["probabilities"] = [float("nan"), .3, .7]
        self.assertEqual(self.check()["reason"], "INVALID_PROBABILITIES")

    def test_result_before_regulation_end_rejected(self):
        self.data["fixtures"][0]["result_received_utc"] = "2026-11-08T21:00:00Z"
        self.assertEqual(self.check()["reason"], "RESULT_RECORDED_BEFORE_REGULATION_END")

    def test_after_kickoff_cutoff_rejected(self):
        self.data["fixtures"][0]["as_of_utc"] = "2026-11-08T20:00:00Z"
        self.assertEqual(self.check()["reason"], "NOT_PREMATCH_CUTOFF")

    def test_native_id_cannot_have_control_characters(self):
        self.data["fixtures"][0]["fixture_id"] = "match-0\nspoof"
        self.assertEqual(self.check()["reason"], "INVALID_NATIVE_ID")

    def test_all_pairs_required_or_no_partial_scoring(self):
        self.data["model_a"][1]["probabilities"] = [0.99, 0.5, 0.01]
        report = self.check()
        self.assertEqual(report["reason"], "INVALID_PROBABILITIES")
        self.assertNotIn("unverified_diagnostic_metrics", report)

    def test_empty_cohort_rejected(self):
        self.data["fixtures"] = []
        self.assertEqual(self.check()["reason"], "INVALID_COHORT_SIZE")


if __name__ == "__main__":
    unittest.main()
