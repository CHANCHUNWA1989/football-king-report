import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from provider_schema_bridge import normalize
from provider_ingestion import analyze

NOW=datetime(2026,10,9,14,tzinfo=timezone.utc)
def current():
    return {"success":True,"data":[
        {"event_id":"evt1","sport":"soccer_epl","home_team":"Home","away_team":"Away",
         "start_time":"2026-10-09T13:00:00Z","books":[
            {"book":"book1","market":"totals","updated_at":"2026-10-09T13:59:45Z",
             "outcomes":[{"name":"Under","price":-110,"point":1.75}]},
            {"book":"book2","market":"totals","updated_at":"2026-10-09T13:59:50Z",
             "outcomes":[{"name":"Under","price":-105,"point":1.75}]}]}]}
def case():
    return {"fixture":{"home":"Home","away":"Away","league":"soccer_epl",
                       "event_id":"evt1","independent_fixture_sources":2}}

class ProviderBridgeTests(unittest.TestCase):
    def test_new_provider_schema_converts_american_odds(self):
        r=normalize(current(),sport_key="soccer_epl")
        self.assertEqual(r["events_normalized"],1)
        self.assertEqual(r["events"][0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"],1.909091)

    def test_end_to_end_new_schema_has_research_consensus_only(self):
        r=analyze(case(),current(),now=NOW)
        self.assertEqual(r["analysis"]["research_consensus_groups"],1)
        self.assertEqual(r["analysis"]["status"],"HOLD")
        self.assertFalse(r["analysis"]["can_execute_bet"])

    def test_stale_book_updated_at_is_not_fresh(self):
        d=current()
        for book in d["data"][0]["books"]:
            book["updated_at"]="2026-10-09T13:45:00Z"
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["analysis"]["research_consensus_groups"],0)

    def test_cross_event_id_not_joined(self):
        d=current()
        d["data"][0]["event_id"]="different"
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["analysis"]["research_consensus_groups"],0)

    def test_explicit_decimal_format(self):
        d=current()
        for book in d["data"][0]["books"]:
            book["outcomes"][0]["price"]=1.9
        r=analyze(case(),d,odds_format="decimal",now=NOW)
        self.assertEqual(r["analysis"]["research_consensus_groups"],1)

    def test_wrong_format_fails_closed(self):
        with self.assertRaises(ValueError):
            normalize(current(),sport_key="soccer_epl",odds_format="unknown")

    def test_missing_timestamp_never_validated(self):
        d=current()
        for book in d["data"][0]["books"]:
            del book["updated_at"]
        r=analyze(case(),d,now=NOW)
        self.assertEqual(r["analysis"]["research_consensus_groups"],0)

    def test_wrong_sport_never_associated(self):
        r=normalize(current(),sport_key="soccer_spain_la_liga")
        self.assertEqual(r["events_normalized"],0)

    def test_invalid_price_dropped(self):
        d=current()
        d["data"][0]["books"][0]["outcomes"][0]["price"]=True
        r=normalize(d,sport_key="soccer_epl")
        self.assertEqual(r["rejections"]["INVALID_PRICE"],1)

    def test_missing_fixture_is_hold(self):
        r=analyze({},current(),now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["reason"],"MISSING_SPORT_KEY")

    def test_legacy_v4_decimal(self):
        d=[{"id":"evt1","sport_key":"soccer_epl","home_team":"Home","away_team":"Away",
            "commence_time":"2026-10-09T13:00:00Z",
            "bookmakers":[{"key":"a","markets":[{"key":"h2h",
                "last_update":"2026-10-09T13:59:50Z",
                "outcomes":[{"name":"Home","price":2.2}]}]}]}]
        r=normalize(d,sport_key="soccer_epl",odds_format="decimal")
        self.assertEqual(r["events_normalized"],1)
        self.assertEqual(r["events"][0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"],2.2)

if __name__=="__main__":
    unittest.main()
