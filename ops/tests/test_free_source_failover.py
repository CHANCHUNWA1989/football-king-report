"""Simulated primary outage, fallback and no-source states."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from free_source_failover import route


class FreeSourceFailoverTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.primary = {"generated_utc": self.now.isoformat(), "source_checked_utc": self.now.isoformat(), "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED", "providers": [
            {"provider": "thesportsdb", "status": "PARTIAL_COVERAGE", "sampled_fixture_count": 2}]}
        self.backup = {"generated_utc": self.now.isoformat(), "source_as_of_utc": self.now.isoformat(), "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                       "backup_scheduled_fixtures": [
                           {"backup_for_schedule_only": True, "market_confirmed": False,
                            "production_recommendations": "DISABLED",
                            "betting_recommendation": False, "source": "openligadb",
                            "league": "bundesliga", "home": "Bayern", "away": "Dortmund",
                            "kickoff_utc": (self.now + timedelta(days=2)).isoformat()}]}

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

    def test_expired_primary_uses_backup(self):
        self.primary["generated_utc"] = (self.now - timedelta(hours=40)).isoformat()
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "BACKUP_SCHEDULE_ONLY")

    def test_expired_primary_and_backup_fail_closed(self):
        old = (self.now - timedelta(hours=40)).isoformat()
        self.primary["generated_utc"] = old
        self.backup["generated_utc"] = old
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "NO_VERIFIED_SCHEDULE_SOURCE")

    def test_primary_partial_with_samples_is_usable(self):
        self.primary["providers"][0]["status"] = "PARTIAL"
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "PRIMARY_SCHEDULE_ONLY")

    def test_primary_actual_collection_stale_even_if_dashboard_fresh(self):
        self.primary["source_checked_utc"] = (
            self.now - timedelta(hours=40)).isoformat()
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "BACKUP_SCHEDULE_ONLY")

    def test_backup_actual_collection_stale_even_if_dashboard_fresh(self):
        self.primary["status"] = "HOLD"
        self.backup["source_as_of_utc"] = (
            self.now - timedelta(hours=40)).isoformat()
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "NO_VERIFIED_SCHEDULE_SOURCE")

    def test_malformed_provider_rows_do_not_crash(self):
        self.primary["providers"] = [None, {}, {"status": "PARTIAL"},
                                      {"provider": "thesportsdb", "status": "PARTIAL",
                                       "sampled_fixture_count": "2"}]
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "BACKUP_SCHEDULE_ONLY")

    def test_real_collector_overlay_feeds_primary_router(self):
        # End-to-end, no-network regression: catches changes in the
        # provider status vocabulary between collection and routing.
        import json
        from secondary_sources import collect
        from source_overlay import build as overlay_build

        when = self.now + timedelta(days=2)
        event = {
            "events": [{"idLeague": "4328", "idEvent": "one-epl-fixture",
                        "strHomeTeam": "Arsenal", "strAwayTeam": "Chelsea",
                        "strTimestamp": when.isoformat(), "strStatus": "NS"}]
        }

        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return json.dumps(event).encode("utf-8")[:limit]

        audit = collect(now=self.now, keys={}, requester=lambda req, timeout: Response())
        shadow = {"status": "SHADOW_ONLY", "production_recommendations": "DISABLED",
                  "predictions": []}
        overlay = overlay_build(shadow, audit, now=datetime.now(timezone.utc))
        self.assertEqual(overlay["providers"][0]["status"], "PARTIAL_COVERAGE")
        outcome = route(overlay, None)
        self.assertEqual(outcome["status"], "PRIMARY_SCHEDULE_ONLY")
        self.assertEqual(outcome["available_primary_providers"], ["thesportsdb"])

    def test_primary_research_source_cannot_claim_betting_permission(self):
        self.primary["production_recommendations"] = "ENABLED"
        self.assertEqual(route(self.primary, None, now=self.now)["status"],
                         "NO_VERIFIED_SCHEDULE_SOURCE")

    def test_unknown_and_unhashable_provider_metadata_do_not_count(self):
        self.primary["providers"] = [
            {"provider": ["thesportsdb"], "status": "PARTIAL", "sampled_fixture_count": 2},
            {"provider": "bogus-feed", "status": "OK", "sampled_fixture_count": 99},
        ]
        self.assertEqual(route(self.primary, None, now=self.now)["status"],
                         "NO_VERIFIED_SCHEDULE_SOURCE")

    def test_fake_backup_fixture_is_not_accepted(self):
        self.primary["status"] = "HOLD"
        entry = self.backup["backup_scheduled_fixtures"][0]
        entry["source"] = "untrusted"
        self.assertEqual(route(self.primary, self.backup, now=self.now)["status"],
                         "NO_VERIFIED_SCHEDULE_SOURCE")
        entry["source"] = "openligadb"
        entry["kickoff_utc"] = (self.now - timedelta(minutes=5)).isoformat()
        self.assertEqual(route(self.primary, self.backup, now=self.now)["backup_fixture_count"], 0)

    def test_duplicate_backup_fixture_not_double_counted(self):
        self.primary["status"] = "HOLD"
        self.backup["backup_scheduled_fixtures"].append(
            dict(self.backup["backup_scheduled_fixtures"][0]))
        result = route(self.primary, self.backup, now=self.now)
        self.assertEqual(result["status"], "BACKUP_SCHEDULE_ONLY")
        self.assertEqual(result["backup_fixture_count"], 1)

    def test_naive_now_rejected(self):
        with self.assertRaisesRegex(ValueError, "NAIVE_NOW"):
            route(self.primary, self.backup, now=datetime(2026, 10, 11))

    def test_untrusted_backup_never_used(self):
        self.primary["status"] = "HOLD"
        self.backup["production_recommendations"] = "ENABLED"
        result = route(self.primary, self.backup)
        self.assertEqual(result["status"], "NO_VERIFIED_SCHEDULE_SOURCE")


if __name__ == "__main__":
    unittest.main()
