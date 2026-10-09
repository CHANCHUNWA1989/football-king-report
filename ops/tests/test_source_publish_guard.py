"""Every extra source report is sanitized, bounded and cannot spoof market odds."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from secondary_sources import collect, SD_BD
from source_publish_guard import verify, should_replace


class MockResponse:
    def __init__(self, item):
        import json
        self.raw=json.dumps(item).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,size): return self.raw[:size]


class SourcePublishingTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        def fake(req,timeout):
            ident=int(req.full_url.rsplit("=",1)[-1])
            return MockResponse({"events":[{
                "idEvent":str(ident),"idLeague":str(ident),
                "strHomeTeam":"A","strAwayTeam":"B",
                "strTimestamp":(self.now+timedelta(days=2)).isoformat(),
                "strStatus":"NS"}]})
        self.payload=collect(now=self.now,keys={},requester=fake)

    def test_four_providers_can_be_published(self):
        self.assertIsNotNone(verify(self.payload))
        self.assertEqual(len(self.payload["sampled_fixtures"]),6)

    def test_free_provider_inflated_league_count_rejected(self):
        p=copy.deepcopy(self.payload)
        p["providers"][0]["counts_by_league"]["epl"] += 10
        p["providers"][0]["sampled_fixture_count"] += 10
        with self.assertRaisesRegex(ValueError,"SOURCE_COVERAGE_TOTALS_MISMATCH"):
            verify(p)

    def test_free_provider_missing_fixture_rejected(self):
        p=copy.deepcopy(self.payload)
        p["sampled_fixtures"].pop()
        with self.assertRaisesRegex(ValueError,"SOURCE_COVERAGE_TOTALS_MISMATCH"):
            verify(p)

    def test_free_provider_invalid_count_type_rejected(self):
        p=copy.deepcopy(self.payload)
        p["providers"][0]["counts_by_league"]["epl"] = "100"
        with self.assertRaisesRegex(ValueError,"SOURCE_COVERAGE_TOTALS_MISMATCH"):
            verify(p)

    def test_no_raw_bookmaker_price_field(self):
        p=copy.deepcopy(self.payload)
        p["sampled_fixtures"][0]["price"]=1.95
        with self.assertRaisesRegex(ValueError,"RAW_SOURCE_DATA_NOT_ALLOWED"):
            verify(p)

    def test_research_only_never_unlocks_betting(self):
        p=copy.deepcopy(self.payload)
        p["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"MISLEADING_SOURCE_PROVENANCE"):
            verify(p)

    def test_inflated_claim_six_league_verified_rejected(self):
        p=copy.deepcopy(self.payload)
        p["six_league_independent_results_verified"]=True
        with self.assertRaisesRegex(ValueError,"MISLEADING_SOURCE_PROVENANCE"):
            verify(p)

    def test_missing_provider_rejected(self):
        p=copy.deepcopy(self.payload)
        p["providers"].pop()
        with self.assertRaisesRegex(ValueError,"INVALID_PROVIDER_COLLECTION"):
            verify(p)

    def test_bogus_provider_budget_rejected(self):
        p=copy.deepcopy(self.payload)
        p["providers"][0]["calls_attempted"]=500
        with self.assertRaisesRegex(ValueError,"UNSAFE_SOURCE_PROVIDER_METADATA"):
            verify(p)

    def test_identical_snapshot_is_idempotent(self):
        self.assertFalse(should_replace(self.payload,self.payload))

    def test_conflicting_snapshot_same_timestamp_rejected(self):
        p=copy.deepcopy(self.payload)
        p["providers"][0]["warnings"].append("fake")
        with self.assertRaisesRegex(ValueError,"SAME_TIMESTAMP_DIFFERENT_SOURCE_REPORT"):
            should_replace(p,self.payload)

    def test_future_timestamp_rejected(self):
        p=copy.deepcopy(self.payload)
        p["collected_utc"]=(self.now+timedelta(hours=4)).isoformat()
        with self.assertRaises(ValueError):
            verify(p)

    def test_no_api_key_field_allowed(self):
        p=copy.deepcopy(self.payload)
        p["unsafe_api_key"]="secret"
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_PRIVATE_OR_BETTING_FIELDS"):
            verify(p)


    def test_bad_provider_league_counts_type_fails_closed(self):
        p=copy.deepcopy(self.payload)
        p["providers"][0]["counts_by_league"]=["epl"]
        with self.assertRaisesRegex(ValueError,"UNSAFE_SOURCE_PROVIDER_METADATA"):
            verify(p)

    def test_bad_fixture_status_rejected(self):
        p=copy.deepcopy(self.payload)
        p["sampled_fixtures"][0]["status"]="BETTABLE"
        with self.assertRaisesRegex(ValueError,"UNSAFE_SOURCE_FIXTURE"):
            verify(p)

    def test_non_string_fixture_team_rejected(self):
        p=copy.deepcopy(self.payload)
        p["sampled_fixtures"][0]["home"]={"name":"Injection"}
        with self.assertRaisesRegex(ValueError,"UNSAFE_SOURCE_FIXTURE"):
            verify(p)

if __name__=="__main__":
    unittest.main()
