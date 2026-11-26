import unittest
from datetime import datetime, timedelta, timezone
from ops.coverage_reconciliation import reconcile, STATUS_SCHEMA
NOW = datetime(2026,11,26,10,tzinfo=timezone.utc)

class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.status = dict(schema=STATUS_SCHEMA, production_recommendations="DISABLED",
            collected_utc=NOW.isoformat(), source_scheduled_fixtures=3,
            retained_fixture_observations=2, fixture_observations_omitted=1,
            catalogue_cards_total=5, catalogue_cards_examined=5,
            catalogue_cards_omitted_by_bound=0, eligible_catalogue_leagues=2,
            schedule_only_catalogue_leagues=1, requested_leagues=2,
            eligible_not_selected=1, ambiguous_candidate_entries=2)
        self.world = dict(collected_utc=NOW.isoformat(), production_recommendations="DISABLED",
            leagues=[dict(fixture_observations=[{},{}])])
    def run_report(self):
        return reconcile(self.status,self.world,NOW)
    def test_counts_reconciled_but_never_coverage(self):
        r=self.run_report()
        self.assertEqual(r["reason"],"LOCAL_COUNTS_RECONCILED_NOT_GLOBAL_COVERAGE")
        self.assertFalse(r["global_coverage_complete"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_invalid_count_and_mismatch(self):
        for value in (True, -1, 4):
            self.status["retained_fixture_observations"]=value
            self.assertIsNone(self.run_report()["counts"])
    def test_mismatched_clock_and_stale(self):
        self.world["collected_utc"]=(NOW-timedelta(minutes=1)).isoformat()
        self.assertIsNone(self.run_report()["counts"])
        self.status["collected_utc"]=self.world["collected_utc"]=(NOW-timedelta(days=1)).isoformat()
        self.assertIsNone(self.run_report()["counts"])
    def test_unsafe_status(self):
        self.status["production_recommendations"]="ENABLED"
        self.assertIsNone(self.run_report()["counts"])
