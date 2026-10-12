"""No-cost historical FT recovery must never fabricate independent evidence."""
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from free_score_history import recover, MAX_JSON_BYTES
from forward_validation import extend
from source_publish_guard import PROVIDERS, LEAGUES


class ArchivedFreeResultsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 12, 8, 40, tzinfo=timezone.utc)
        self.kick = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
        self.snapshot_at = self.kick + timedelta(hours=2, minutes=20)

    def snapshot(self, score=(0, 2), *, captured=None, event_id="fixture-1"):
        captured = captured or self.snapshot_at
        counts = {league: 0 for league in LEAGUES}
        counts["epl"] = 1
        providers = []
        for provider in PROVIDERS:
            active = provider == "thesportsdb"
            providers.append({
                "provider": provider,
                "status": "PARTIAL_COVERAGE" if active else "NOT_CONFIGURED",
                "configured": active, "calls_attempted": 1 if active else 0,
                "counts_by_league": counts if active else
                    {league: 0 for league in LEAGUES},
                "sampled_fixture_count": 1 if active else 0,
                "league_result_verification_complete": False,
                "can_replace_1x2_market": False,
                "original_bookmaker_odds_redistributed": False,
                "production_recommendations": "DISABLED",
                **({"recent_final_score_observations": 1} if active else {}),
            })
        return {
            "schema": "football-king-extra-source-audit-v1",
            "started_utc": (captured - timedelta(minutes=3)).isoformat(),
            "collected_utc": captured.isoformat(),
            "source_tier": "RESEARCH_ONLY", "status": "RESEARCH_ONLY",
            "providers": providers,
            "sampled_fixtures": [{
                "league": "epl", "home": "Everton", "away": "Arsenal",
                "provider": "thesportsdb", "provider_event_id": event_id,
                "kickoff_utc": self.kick.isoformat(),
                "status": "FINISHED", "score_ft": list(score),
            }],
            "coverage_is_complete": False,
            "six_league_independent_results_verified": False,
            "odds_fallback_confirmed": False,
            "original_api_payload_redistributed": False,
            "production_recommendations": "DISABLED",
        }

    def archive(self, root, doc, day="09", filename="run.json.gz"):
        p = root / "2026" / "10" / day / filename
        p.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(p, "wt", encoding="utf-8") as out:
            json.dump(doc, out)
        return p

    def test_two_day_old_snapshot_recovers_without_new_api_request(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root, self.snapshot())
            rows, report = recover(root, self.now)
            self.assertEqual(report["status"], "RESEARCH_ONLY")
            self.assertEqual(report["historical_finished_candidates"], 1)
            self.assertEqual(report["executed_api_queries"], 0)
            self.assertFalse(rows[0]["independently_verified"])
            self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_same_provider_same_score_across_snapshots_is_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root, self.snapshot(), filename="run-a.json.gz")
            self.archive(root, self.snapshot(captured=self.snapshot_at+timedelta(hours=1)),
                         filename="run-b.json.gz")
            rows, report = recover(root, self.now)
            self.assertEqual(len(rows), 1)
            self.assertEqual(report["same_provider_repeated_observations_suppressed"], 1)

    def test_conflicting_score_is_preserved_and_quarantined_by_settlement(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root, self.snapshot((0, 2)), filename="run-a.json.gz")
            self.archive(root, self.snapshot((2, 0),
                         captured=self.snapshot_at+timedelta(hours=1)),
                         filename="run-b.json.gz")
            rows, report = recover(root, self.now)
            self.assertEqual(len(rows), 2)
            self.assertEqual(report["historical_finished_candidates"], 2)
            record = {
                "league": "epl", "home": "Everton", "away": "Arsenal",
                "kickoff_utc": self.kick.isoformat(),
                "prediction_utc": (self.kick-timedelta(hours=2)).isoformat(),
                "market_snapshot_utc": (self.kick-timedelta(hours=3)).isoformat(),
                "model": [.3, .3, .4], "market": [.2, .3, .5],
                "production_recommendations": "DISABLED",
            }
            key = ("epl", "everton", "arsenal", self.kick.isoformat())
            report_doc = {"checked_utc": self.now.isoformat(),
                          "fixtures": {"matches": []}}
            settled = extend({}, [(key, record)], report_doc, free_result_rows=rows)
            self.assertEqual(settled["n"], 0)
            self.assertEqual(settled["production_recommendations"], "DISABLED")

    def test_valid_old_archive_can_settle_only_previously_sealed_case(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.archive(root, self.snapshot())
            rows, _ = recover(root, self.now)
            record = {
                "league": "epl", "home": "Everton", "away": "Arsenal",
                "kickoff_utc": self.kick.isoformat(),
                "prediction_utc": (self.kick-timedelta(hours=2)).isoformat(),
                "market_snapshot_utc": (self.kick-timedelta(hours=3)).isoformat(),
                "model": [.3, .3, .4], "market": [.2, .3, .5],
                "production_recommendations": "DISABLED",
            }
            key = ("epl", "everton", "arsenal", self.kick.isoformat())
            report_doc = {"checked_utc": self.now.isoformat(),
                          "fixtures": {"matches": []}}
            settled = extend({}, [(key, record)], report_doc, free_result_rows=rows)
            self.assertEqual(settled["n"], 1)
            self.assertEqual(settled["samples"][0]["y"], 2)
            self.assertFalse(settled["samples"][0]["fixture_result_source_independently_verified"])
            self.assertEqual(settled["production_recommendations"], "DISABLED")
            self.assertEqual(extend({}, [], report_doc, free_result_rows=rows)["n"], 0)

    def test_tampered_future_old_and_oversized_snapshots_never_count(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bad = self.snapshot()
            bad["production_recommendations"] = "ENABLED"
            self.archive(root, bad, filename="bad.json.gz")
            too_early = self.snapshot(captured=self.kick+timedelta(minutes=65))
            self.archive(root, too_early, filename="early.json.gz")
            future = self.snapshot(captured=self.now+timedelta(hours=1))
            self.archive(root, future, filename="future.json.gz")
            path = self.archive(root, self.snapshot(), filename="huge.json.gz")
            with gzip.open(path, "wb") as out:
                out.write(b" " * (MAX_JSON_BYTES + 1))
            rows, report = recover(root, self.now)
            self.assertEqual(rows, [])
            self.assertEqual(report["snapshots_rejected"], 3)
            self.assertEqual(report["historical_finished_candidates"], 0)

    def test_invalid_timestamp_cap_and_missing_archive_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows, report = recover(root, self.now)
            self.assertEqual(rows, [])
            self.assertEqual(report["status"], "HOLD")
            with self.assertRaisesRegex(ValueError, "INVALID_HISTORY_CANDIDATE_CAP"):
                recover(root, self.now, max_candidates=101)
            with self.assertRaisesRegex(ValueError, "NAIVE_RECOVERY_CLOCK"):
                recover(root, datetime(2026, 10, 12))


if __name__ == "__main__":
    unittest.main()
