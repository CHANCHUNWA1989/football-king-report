import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_quote_gate import extract

NOW="2026-10-09T14:00:00Z"
def event():
    return [{"id":"fixture1","sport_key":"soccer_epl",
        "commence_time":"2026-10-09T13:00:00Z",
        "home_team":"Home","away_team":"Away",
        "bookmakers":[{"key":"sample","last_update":"2026-10-09T14:00:00Z",
            "markets":[{"key":"totals","last_update":"2026-10-09T13:59:30Z",
                "outcomes":[{"name":"Under","price":1.74,"point":1.75},
                            {"name":"Over","price":2.06,"point":1.75}]},
                       {"key":"spreads","last_update":"2026-10-09T13:59:20Z",
                "outcomes":[{"name":"Home","price":1.88,"point":0.25},
                            {"name":"Away","price":1.99,"point":-0.25}]},
                       {"key":"h2h","last_update":"2026-10-09T13:59:45Z",
                "outcomes":[{"name":"Home","price":2.2},
                            {"name":"Draw","price":3.1},
                            {"name":"Away","price":3.4}]}]}]}]

def run(payload):
    return extract(payload,captured_utc=NOW,league="soccer_epl",
                   home="Home",away="Away")

class QuoteGateTests(unittest.TestCase):
    def test_seven_quotes_across_three_markets(self):
        result=run(event())
        self.assertEqual(result["quotes_accepted"],7)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertFalse(result["executable_bookmaker_price_verified"])
        self.assertIsNone(result["recommendation"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertTrue(all(x["status"]=="FRESH_OBSERVATION_NOT_EXECUTABLE"
                            for x in result["quotes"]))

    def test_market_timestamp_missing_rejects_even_if_bookmaker_recent(self):
        d=event()
        del d[0]["bookmakers"][0]["markets"][0]["last_update"]
        result=run(d)
        self.assertEqual(result["quotes_accepted"],5)
        self.assertEqual(result["reject_reasons"]["MISSING_MARKET_LAST_UPDATE"],1)

    def test_old_market_time_rejects(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["last_update"]="2026-10-09T13:40:00Z"
        self.assertEqual(run(d)["reject_reasons"]["STALE_OR_FUTURE_MARKET"],1)

    def test_future_market_clock_rejects(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["last_update"]="2026-10-09T14:03:00Z"
        self.assertEqual(run(d)["quotes_accepted"],5)

    def test_invalid_price_boolean_and_nan_rejected(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"]=True
        d[0]["bookmakers"][0]["markets"][0]["outcomes"][1]["price"]=float("nan")
        result=run(d)
        self.assertEqual(result["quotes_accepted"],5)
        self.assertEqual(result["reject_reasons"]["INVALID_DECIMAL_PRICE"],2)

    def test_invalid_quarter_line_rejected(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["point"]=1.33
        self.assertEqual(run(d)["reject_reasons"]["INVALID_ASIAN_POINT"],1)

    def test_duplicate_quote_rejected(self):
        d=event()
        d[0]["bookmakers"][0]["markets"][0]["outcomes"].append(
            dict(d[0]["bookmakers"][0]["markets"][0]["outcomes"][0]))
        self.assertEqual(run(d)["reject_reasons"]["DUPLICATE_QUOTE"],1)

    def test_unmatched_team_does_not_cross_join(self):
        d=event()
        d[0]["home_team"]="Another"
        self.assertEqual(run(d)["quotes_accepted"],0)
        self.assertEqual(run(d)["status"],"HOLD")

    def test_wrong_sport_key_rejected(self):
        d=event()
        d[0]["sport_key"]="soccer_spain_la_liga"
        self.assertEqual(run(d)["reject_reasons"]["WRONG_SPORT_KEY"],1)

    def test_naive_clock_fails_closed(self):
        with self.assertRaises(ValueError):
            extract(event(),captured_utc="2026-10-09T14:00:00",
                    league="soccer_epl",home="Home",away="Away")

    def test_overlong_input_rejected(self):
        with self.assertRaises(ValueError):
            run(event()*201)

    def test_missing_spread_point_rejected(self):
        d=event()
        del d[0]["bookmakers"][0]["markets"][1]["outcomes"][0]["point"]
        self.assertEqual(run(d)["reject_reasons"]["INVALID_ASIAN_POINT"],1)

if __name__=="__main__":
    unittest.main()
