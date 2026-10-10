"""Simulated primary outage, fallback and no-source states."""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from free_source_failover import route


class FreeSourceFailoverTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.primary = {"generated_utc": self.now.isoformat(), "status": "RESEARCH_ONLY", "providers": [
            {"provider": "thesportsdb", "status": "FETCHED", "sampled_fixture_count": 2}]}
        self.backup = {"generated_utc": self.now.isoformat(), "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                       "backup_scheduled_fixtures": [
                           {"backup_for_schedule_only": True, "market_confirmed": False,
                            "production_recommendations": "DISABLED"}]}

    def test_primary_available(self):
        result = route(self.primary, self.backup)
        self.assertEqual(result["status"], "PRIMARY_SCHEDULE_ONLY")
        self.assertFalse(result["executable_odds_fallback_available"])

    def test_primary_api_outage_uses_schedule_backup(self):
        self.primary["status"] = "HOLD"
        result = route(self.primary, self.backup)
        self.assertEqual(result["status"], "BACKUP_SCHEDULE_ONLY")
        self.assertEqual(result["selected_source"], "openligadb")
        self.assertFalse(result["can_generate_model_predictions"])

    def test_all_sources_outage_fails_closed(self):
        result = route(None, None)
        self.assertEqual(result["status"], "NO_VERIFIED_SCHEDULE_SOURCE")
        self.assertIsNone(result["selected_source"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_untrusted_backup_never_used(self):
        self.primary["status"] = "HOLD"
        self.backup["production_recommendations"] = "ENABLED"
        result = route(self.primary, self.backup)
        self.assertEqual(result["status"], "NO_VERIFIED_SCHEDULE_SOURCE")


if __name__ == "__main__":
    unittest.main()
