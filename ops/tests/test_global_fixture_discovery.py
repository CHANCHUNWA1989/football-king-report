import copy
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from global_fixture_discovery import collect,parse,verify

NOW=datetime(2026,10,10,0,0,tzinfo=timezone.utc)
GOOD={"data":[{"id":1,"league":{"name":"K League 1"},
 "home_team":{"name":"Seoul"},"away_team":{"name":"Ulsan"},
 "kickoff_utc":"2026-10-10T10:00:00Z"},
 {"id":2,"competition":"J1 League","home":"Kobe","away":"Tokyo",
 "kickoff":"2026-10-10T11:00:00+00:00"}]}

class GlobalDiscoveryTests(unittest.TestCase):
    def test_accepted_rows_are_not_betting_recommendations(self):
        d=collect(NOW,loader=lambda url: GOOD if url.endswith("10") else {"data":[]})
        self.assertTrue(verify(d))
        self.assertEqual(d["observed_competition_count"],2)
        self.assertEqual(d["fixture_count"],2)
        self.assertFalse(d["provider_live_access_confirmed"])
        self.assertEqual(d["production_recommendations"],"DISABLED")
        self.assertTrue(all(not r["qualifies_for_recommendation"] for r in d["fixtures"]))

    def test_duplicate_event_id_quarantines_day(self):
        payload=copy.deepcopy(GOOD)
        payload["data"][1]["id"]=1
        d=collect(NOW,loader=lambda url: payload if url.endswith("10") else {"data":[]})
        self.assertEqual(d["fixture_count"],0)
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["request_failures"][0]["reason"],"ValueError")

    def test_no_naive_time_or_wrong_date(self):
        payload={"data":[{"id":3,"league":"K League 1","home":"A","away":"B",
                          "kickoff":"2026-10-10T10:00:00"},
                         {"id":4,"league":"K League 1","home":"A","away":"B",
                          "kickoff":"2026-10-12T10:00:00Z"}]}
        a,rejected=parse(payload,"2026-10-10")
        self.assertEqual(len(a),0)
        self.assertEqual(rejected,2)

    def test_unavailable_api_is_hold_not_fabricated_global_coverage(self):
        d=collect(NOW,loader=lambda url: (_ for _ in ()).throw(TimeoutError()))
        self.assertTrue(verify(d))
        self.assertEqual(d["observed_competition_count"],0)
        self.assertEqual(d["status"],"HOLD")

    def test_guard_blocks_fabricated_recommendations(self):
        d=collect(NOW,loader=lambda url: GOOD if url.endswith("10") else {"data":[]})
        d["fixtures"][0]["qualifies_for_recommendation"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_GLOBAL_ROW"):
            verify(d)

    def test_guard_blocks_fabricated_coverage(self):
        d=collect(NOW,loader=lambda url: GOOD if url.endswith("10") else {"data":[]})
        d["observed_competition_count"]=120
        with self.assertRaisesRegex(ValueError,"FABRICATED_GLOBAL_COVERAGE"):
            verify(d)

    def test_guard_blocks_market_claims(self):
        d=collect(NOW,loader=lambda url: GOOD if url.endswith("10") else {"data":[]})
        d["market_odds_available"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_GLOBAL_PROVENANCE"):
            verify(d)

if __name__=="__main__":
    unittest.main()
