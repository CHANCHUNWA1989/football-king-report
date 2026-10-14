import unittest
from shadow_daily_report import report

SEALED={"fixture_id":"f1","kickoff_utc":"2026-10-12T12:00:00Z",
        "sealed_at_utc":"2026-10-12T10:00:00Z",
        "market_snapshot_utc":"2026-10-12T09:30:00Z",
        "model":[0.6,0.2,0.2],"market":[0.4,0.3,0.3]}

def ft(provider, group):
    return {"fixture_id":"f1","status":"FT","provider_id":provider,
            "independent_group_id":group,"published_utc":"2026-10-12T15:00:00Z",
            "home_goals":2,"away_goals":1,
            "source_url":("https://api.openligadb.de/getmatchdata/bl1/2026" if provider=="OpenLigaDB" else "https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json"),
            "raw_sha256":"a"*64}

class DailyReportTests(unittest.TestCase):
    def test_empty_inputs_show_no_claim(self):
        data=report([],[])
        self.assertEqual(data["valid_fixtures"],0)
        self.assertIsNone(data["models"]["market_75"]["accuracy"])
        self.assertEqual(data["production_recommendations"],"DISABLED")

    def test_one_independent_source_stays_empty(self):
        self.assertEqual(report([SEALED],[ft("OpenLigaDB","openligadb")])["valid_fixtures"],0)

    def test_two_independent_sources_scored(self):
        data=report([SEALED],[ft("OpenLigaDB","openligadb"),ft("OpenFootball","openfootball")])
        self.assertEqual(data["valid_fixtures"],1)
        self.assertEqual(data["remaining"],999)

    def test_duplicate_seals_count_once(self):
        data=report([SEALED,SEALED],[ft("OpenLigaDB","openligadb"),ft("OpenFootball","openfootball")])
        self.assertEqual(data["valid_fixtures"],1)

if __name__=="__main__":
    unittest.main()
