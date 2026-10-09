import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrated_market_consensus import analyze

NOW=datetime(2026,10,9,14,0,tzinfo=timezone.utc)

def fixture():
    return {"fixture":{"home":"Home","away":"Away","league":"soccer_epl",
                       "event_id":"event-1","independent_fixture_sources":2}}

def odds():
    return [{"id":"event-1","sport_key":"soccer_epl",
             "home_team":"Home","away_team":"Away",
             "commence_time":"2026-10-09T13:00:00Z",
             "bookmakers":[
               {"key":"a","markets":[{"key":"totals",
                "last_update":"2026-10-09T13:59:45Z",
                "outcomes":[{"name":"Under","price":1.80,"point":1.75}]}]},
               {"key":"b","markets":[{"key":"totals",
                "last_update":"2026-10-09T13:59:40Z",
                "outcomes":[{"name":"Under","price":1.85,"point":1.75}]}]}]}]

class IntegratedTests(unittest.TestCase):
    def test_two_bookmaker_consensus_from_real_validator(self):
        r=analyze(fixture(),odds(),now=NOW)
        self.assertEqual(r["research_consensus_groups"],1)
        self.assertEqual(r["consensus_groups"][0]["bookmakers"],2)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["can_execute_bet"])
        self.assertIsNone(r["recommendation"])

    def test_one_bookmaker_not_consensus(self):
        d=odds()
        d[0]["bookmakers"].pop()
        r=analyze(fixture(),d,now=NOW)
        self.assertEqual(r["research_consensus_groups"],0)

    def test_different_line_cannot_form_consensus(self):
        d=odds()
        d[0]["bookmakers"][1]["markets"][0]["outcomes"][0]["point"]=1.5
        self.assertEqual(analyze(fixture(),d,now=NOW)["research_consensus_groups"],0)

    def test_cross_match_id_cannot_form_consensus(self):
        d=odds()
        d[0]["id"]="another-id"
        r=analyze(fixture(),d,now=NOW)
        self.assertEqual(r["research_consensus_groups"],0)
        self.assertEqual(r["consensus_groups"],[])

    def test_stale_market_never_forms_consensus(self):
        d=odds()
        for book in d[0]["bookmakers"]:
            book["markets"][0]["last_update"]="2026-10-09T13:50:00Z"
        self.assertEqual(analyze(fixture(),d,now=NOW)["research_consensus_groups"],0)

    def test_no_fixture_never_joins(self):
        r=analyze({},odds(),now=NOW)
        self.assertEqual(r["research_consensus_groups"],0)
        self.assertEqual(r["status"],"HOLD")

    def test_untrusted_case_claims_cannot_unlock(self):
        c=fixture()
        c["market"]={"bookmaker_quote_executable_verified":True}
        r=analyze(c,odds(),now=NOW)
        self.assertIn("BOOKMAKER_EXECUTION_NOT_VERIFIED",r["blockers"])
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_future_quote_cannot_form_consensus(self):
        d=odds()
        for book in d[0]["bookmakers"]:
            book["markets"][0]["last_update"]="2026-10-09T14:05:00Z"
        self.assertEqual(analyze(fixture(),d,now=NOW)["research_consensus_groups"],0)

if __name__=="__main__":
    unittest.main()
