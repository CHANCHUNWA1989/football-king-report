import copy
import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ops.targeted_historical_gap_audit import audit, GAP
from ops.source_publish_guard import LEAGUES, PROVIDERS


class TargetedHistoricalGapAuditTests(unittest.TestCase):
    def setUp(self):
        self.ko = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
        self.now = self.ko + timedelta(days=48)
        self.queue = {"schema": "football-king-forward-cohort-backlog-v1",
                      "as_of_utc": self.now.isoformat(), "production_recommendations": "DISABLED",
                      "pending_fixtures_not_displayed": 0, "unmatched_finished_result_backlog": 1,
                      "pending_fixtures": [{"league": "epl", "home_id": "evertonfc", "away_id": "arsenalfc",
                           "kickoff_utc": self.ko.isoformat(), "state": GAP,
                           "independently_verified": False, "production_recommendations": "DISABLED"}]}

    def snapshot(self, score=(1, 0), start=None, native="one", home="Everton"):
        start = start or self.ko + timedelta(hours=3)
        providers = []
        for p in PROVIDERS:
            active = p == "thesportsdb"
            providers.append({"provider": p, "status": "PARTIAL" if active else "NOT_CONFIGURED",
                "configured": active, "calls_attempted": int(active),
                "counts_by_league": {l: int(active and l == "epl") for l in LEAGUES},
                "sampled_fixture_count": int(active), "league_result_verification_complete": False,
                "can_replace_1x2_market": False, "original_bookmaker_odds_redistributed": False,
                "production_recommendations": "DISABLED"})
        return {"schema": "football-king-extra-source-audit-v1", "started_utc": start.isoformat(),
                "collected_utc": (start+timedelta(minutes=1)).isoformat(), "providers": providers,
                "sampled_fixtures": [{"league": "epl", "home": home, "away": "Arsenal",
                    "kickoff_utc": self.ko.isoformat(), "provider": "thesportsdb",
                    "provider_event_id": native, "status": "FINISHED", "score_ft": list(score)}],
                "coverage_is_complete": False, "six_league_independent_results_verified": False,
                "odds_fallback_confirmed": False, "original_api_payload_redistributed": False,
                "production_recommendations": "DISABLED"}

    def write(self, root, doc, name="a"):
        folder = Path(root)/"2026/10/11"
        folder.mkdir(parents=True, exist_ok=True)
        (folder/(name+".json.gz")).write_bytes(gzip.compress(json.dumps(doc).encode()))

    def test_old_target_and_curated_alias(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, self.snapshot())
            result = audit(self.queue, root)
            self.assertEqual(result["observed_unverified_targets"], 1)
            self.assertEqual(result["authenticated_samples"], 0)
            self.assertIsNone(result["formal_metrics"])
            self.assertEqual(result["production_recommendations"], "DISABLED")
            self.assertEqual(len(result["targets"][0]["observations"][0]["archive_sha256"]), 64)
            self.assertFalse(result["archive_scope_exhaustive"])

    def test_conflicting_score_or_native_id(self):
        for score, native in [((2,0), "one"), ((1,0), "two")]:
            with self.subTest(score=score, native=native), tempfile.TemporaryDirectory() as root:
                self.write(root, self.snapshot())
                self.write(root, self.snapshot(score, native=native), "b")
                result = audit(self.queue, root)
                self.assertEqual(result["conflicting_targets"], 1)
                self.assertEqual(result["observed_unverified_targets"], 0)

    def test_repeated_identical_observation_not_new_sample(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, self.snapshot())
            self.write(root, self.snapshot(), "b")
            result = audit(self.queue, root)
            self.assertEqual(len(result["targets"][0]["observations"]), 1)

    def test_early_and_wrong_team_excluded(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, self.snapshot(start=self.ko+timedelta(minutes=110)))
            self.write(root, self.snapshot(home="Liverpool"), "b")
            result = audit(self.queue, root)
            self.assertEqual(result["no_match_targets"], 1)

    def test_missing_pair_vs_nonfinal_vs_wrong_kickoff(self):
        for kind, field, reason in (
                ("wrong_team", None, "PAIR_NOT_OBSERVED"),
                ("scheduled", "nonfinal_or_missing_score", "PAIR_OBSERVED_BUT_NO_ELIGIBLE_FINAL"),
                ("wrong_time", "kickoff_mismatch", "PAIR_OBSERVED_BUT_NO_ELIGIBLE_FINAL"),
                ("early", "collection_too_early", "PAIR_OBSERVED_BUT_NO_ELIGIBLE_FINAL")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as root:
                doc = self.snapshot(home="Liverpool" if kind == "wrong_team" else "Everton",
                                    start=self.ko+timedelta(minutes=110) if kind == "early" else None)
                if kind == "scheduled":
                    doc["sampled_fixtures"][0].update(status="SCHEDULED", score_ft=None)
                if kind == "wrong_time":
                    doc["sampled_fixtures"][0]["kickoff_utc"] = (self.ko+timedelta(hours=1)).isoformat()
                self.write(root, doc)
                result = audit(self.queue, root)
                row = result["targets"][0]
                self.assertEqual(row["coverage_reason"], reason)
                self.assertEqual(row["coverage_observation_counts"]["league_rows"], 1)
                if field:
                    self.assertEqual(row["coverage_observation_counts"][field], 1)
                self.assertEqual(result["observed_unverified_targets"], 0)
                self.assertEqual(result["authenticated_samples"], 0)

    def test_no_league_coverage_is_not_a_result(self):
        with tempfile.TemporaryDirectory() as root:
            result = audit(self.queue, root)
            self.assertEqual(result["coverage_reason_counts"], {"LEAGUE_NOT_OBSERVED": 1})
            self.assertTrue(result["selected_window_has_read_errors_or_missing_days"])

    def test_invalid_archive_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            bad = self.snapshot()
            bad["production_recommendations"] = "ENABLED"
            self.write(root, bad)
            result = audit(self.queue, root)
            self.assertEqual(result["rejected_files"], 1)
            self.assertTrue(result["selected_window_has_read_errors_or_missing_days"])

    def test_cap_does_not_return_partial_matches(self):
        with tempfile.TemporaryDirectory() as root:
            self.write(root, self.snapshot())
            self.write(root, self.snapshot((2,0)), "b")
            with patch("ops.targeted_historical_gap_audit.MAX_FILES", 1):
                with self.assertRaisesRegex(ValueError, "TARGETED_FILE_LIMIT"):
                    audit(self.queue, root)

    def test_truncated_queue_and_duplicate_canonical_identity_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            queue = copy.deepcopy(self.queue)
            queue["pending_fixtures_not_displayed"] = 1
            with self.assertRaisesRegex(ValueError, "TRUNCATED"):
                audit(queue, root)
            queue = copy.deepcopy(self.queue)
            row = dict(queue["pending_fixtures"][0], home_id="everton")
            queue["pending_fixtures"].append(row)
            with self.assertRaisesRegex(ValueError, "DUPLICATE"):
                audit(queue, root)


if __name__ == "__main__":
    unittest.main()
