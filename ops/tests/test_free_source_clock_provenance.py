"""A regenerated schedule dashboard is not evidence of a fresh upstream fetch."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from free_source_failover import route


class SourceClockTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 24, 11, tzinfo=timezone.utc)
        clock = self.now.isoformat()
        self.primary = {"generated_utc": clock, "source_checked_utc": clock,
                        "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                        "providers": [{"provider": "thesportsdb", "status": "PARTIAL_COVERAGE",
                                       "sampled_fixture_count": 2}]}
        self.backup = {"generated_utc": clock, "source_as_of_utc": clock,
                       "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                       "backup_scheduled_fixtures": [
                           {"backup_for_schedule_only": True, "market_confirmed": False,
                            "production_recommendations": "DISABLED", "betting_recommendation": False,
                            "source": "openligadb", "league": "bundesliga", "home": "Bayern",
                            "away": "Dortmund", "kickoff_utc": (self.now+timedelta(days=2)).isoformat()}]}

    def test_missing_primary_source_clock_uses_backup(self):
        del self.primary["source_checked_utc"]
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "BACKUP_SCHEDULE_ONLY")
        self.assertEqual(result["available_primary_providers"], [])

    def test_missing_backup_source_clock_rejects_backup(self):
        del self.backup["source_as_of_utc"]
        result = route(None, self.backup, now=self.now)
        self.assertEqual(result["status"], "NO_VERIFIED_SCHEDULE_SOURCE")
        self.assertEqual(result["backup_fixture_count"], 0)

    def test_source_cannot_postdate_overlay(self):
        old = (self.now-timedelta(hours=1)).isoformat()
        self.primary["generated_utc"] = old
        self.backup["generated_utc"] = old
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "NO_VERIFIED_SCHEDULE_SOURCE")

    def test_valid_source_clocks_still_route(self):
        self.primary["source_checked_utc"] = (self.now-timedelta(hours=1)).isoformat()
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "PRIMARY_SCHEDULE_ONLY")
        self.assertFalse(result["executable_odds_fallback_available"])
        self.assertFalse(result["can_generate_model_predictions"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_offset_equivalent_clock_is_accepted(self):
        self.primary["source_checked_utc"] = self.now.astimezone(timezone(timedelta(hours=8))).isoformat()
        self.assertEqual(route(self.primary, None, now=self.now)["status"], "PRIMARY_SCHEDULE_ONLY")

    def test_null_or_naive_source_clock_cannot_route(self):
        for clock in (None, "2026-11-24T11:00:00", 123):
            with self.subTest(clock=clock):
                self.primary["source_checked_utc"] = clock
                self.assertEqual(route(self.primary, None, now=self.now)["status"],
                                 "NO_VERIFIED_SCHEDULE_SOURCE")


if __name__ == "__main__":
    unittest.main()
