"""Offline tests: seven gates only consume verified same-capture fixture evidence."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from six_league_free_upgrade import audit, collect
from six_league_fixture_overlap import compare

class SevenGateCorroborationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.six = collect(token="", now=self.now)
        self.market = {
            "schema": "football-king-market-consensus-v1",
            "as_of_utc": (self.now-timedelta(hours=2)).isoformat(),
            "status": "RESEARCH_ONLY",
            "production_recommendations": "DISABLED",
            "events": [],
        }
        self.source = {"collected_utc":(self.now-timedelta(hours=3)).isoformat()}

    def test_still_seven_and_never_promotes_without_sample(self):
        doc = audit(self.six, self.market, self.source, {"n":1,
                    "production_recommendations":"DISABLED",
                    "results_independently_verified":False})
        self.assertEqual(doc["total"], 7)
        self.assertEqual(doc["checks"][0]["state"], "HOLD")
        self.assertEqual(doc["checks"][5]["state"], "HOLD")
        self.assertIn("candidates=1", doc["checks"][5]["evidence"])
        self.assertEqual(doc["checks"][6]["state"], "PASS")
        self.assertFalse(doc["can_promote_model"])
        self.assertFalse(doc["can_recommend_bets"])

    def test_forged_unvalidated_fixture_report_does_not_promote(self):
        forged = {"schema":"football-king-six-league-two-publisher-fixtures-v1",
                  "captured_utc": self.six["captured_utc"],
                  "at_least_one_other_publisher_agreement":2000,
                  "all_six_leagues_independently_verified":True}
        doc=audit(self.six,self.market,self.source,None,forged)
        self.assertEqual(doc["checks"][0]["state"], "HOLD")
        self.assertEqual(doc["checks"][6]["state"], "PASS")

    def test_unmatched_capture_timestamp_rejected(self):
        forged=compare(None,None,captured_utc=(self.now-timedelta(days=1)).isoformat())
        doc=audit(self.six,self.market,self.source,None,forged)
        self.assertEqual(doc["checks"][0]["state"],"HOLD")

if __name__=="__main__":
    unittest.main()
