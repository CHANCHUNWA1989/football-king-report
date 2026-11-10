import unittest
from ops.the_odds_api_adapter import extract_historical_quotes

def fixture():
    return {"timestamp":"2026-11-06T12:00:00Z","data":[{
        "id":"synthetic-1","commence_time":"2026-11-06T13:00:00Z",
        "home_team":"A","away_team":"B",
        "bookmakers":[{"key":"synthetic_book","markets":[
            {"key":"totals","outcomes":[{"name":"Over","point":2.5,"price":1.91},{"name":"Under","point":2.5,"price":1.95}]},
            {"key":"spreads","outcomes":[{"name":"A","point":-0.25,"price":1.9},{"name":"B","point":0.25,"price":1.9}]}
        ]}]}]}

class AdapterTests(unittest.TestCase):
    def test_declared_provider_namespace_and_native_id_are_preserved(self):
        payload = fixture()
        payload["data"][0]["id"] = "123"
        quotes = extract_historical_quotes(payload)
        self.assertEqual(len(quotes), 4)
        self.assertTrue(all(row.get("event_source") == "the_odds_api_v4" for row in quotes))
        self.assertTrue(all(row["event_id"] == "123" for row in quotes))
        self.assertTrue(all(row["independently_verified"] is False for row in quotes))

    def test_four_quotes(self):
        x=extract_historical_quotes(fixture())
        self.assertEqual(len(x),4)
        self.assertEqual(x[2]["side"],"home")
        self.assertEqual(x[3]["side"],"away")
        self.assertFalse(x[0]["positive_ev_verified"])
    def test_no_forecast_claim(self):
        x=extract_historical_quotes(fixture())[0]
        self.assertNotIn("score_probabilities",x)
        self.assertFalse(x["production_recommendation_allowed"])
    def test_postkickoff_ignored(self):
        x=fixture();x["timestamp"]=x["data"][0]["commence_time"]
        self.assertEqual(extract_historical_quotes(x),[])
    def test_missing_timestamp(self):
        x=fixture();del x["timestamp"]
        with self.assertRaises(ValueError): extract_historical_quotes(x)
    def test_invalid_price(self):
        x=fixture();x["data"][0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"]=1
        with self.assertRaises(ValueError): extract_historical_quotes(x)
    def test_invalid_line(self):
        x=fixture();x["data"][0]["bookmakers"][0]["markets"][0]["outcomes"][0]["point"]=2.3
        with self.assertRaises(ValueError): extract_historical_quotes(x)
    def test_unsupported_market_ignored(self):
        x=fixture();x["data"][0]["bookmakers"][0]["markets"]=[{"key":"h2h","outcomes":[]}]
        self.assertEqual(extract_historical_quotes(x),[])
    def test_invalid_selection(self):
        x=fixture();x["data"][0]["bookmakers"][0]["markets"][0]["outcomes"][0]["name"]="Wrong"
        with self.assertRaises(ValueError): extract_historical_quotes(x)

    def test_handicap_requires_two_distinct_nonempty_team_names(self):
        # Synthetic malformed provider payloads; never evidence of real prices.
        for home, away in ((None, None), (None, "B"), ("A", None),
                           ("", "B"), ("A", ""), (" ", "B"),
                           ("A", "\t"), ("A", "A"), (" A", "A "),
                           (1, "B"), ("A", False), ([], "B")):
            with self.subTest(home=home, away=away):
                x = fixture()
                event = x["data"][0]
                event["home_team"], event["away_team"] = home, away
                event["bookmakers"][0]["markets"] = [{
                    "key": "spreads", "outcomes": [
                        {"name": home, "point": -0.25, "price": 1.9}]}]
                with self.assertRaises(ValueError):
                    extract_historical_quotes(x)

    def test_handicap_missing_teams_and_selection_rejected(self):
        x = fixture()
        event = x["data"][0]
        del event["home_team"], event["away_team"]
        event["bookmakers"][0]["markets"] = [{
            "key": "spreads", "outcomes": [{"point": -0.25, "price": 1.9}]}]
        with self.assertRaises(ValueError):
            extract_historical_quotes(x)

    def test_handicap_selection_must_match_exact_provider_team(self):
        for selection in (None, "", " ", "a", "A ", "Other", 1):
            with self.subTest(selection=selection):
                x = fixture()
                market = x["data"][0]["bookmakers"][0]["markets"][1]
                market["outcomes"][0]["name"] = selection
                with self.assertRaises(ValueError):
                    extract_historical_quotes(x)

    def test_handicap_mapping_uses_provider_home_away_order(self):
        x = fixture()
        event = x["data"][0]
        event["home_team"], event["away_team"] = "B", "A"
        quotes = extract_historical_quotes(x)
        self.assertEqual([(q["side"], q["line"]) for q in quotes[2:]],
                         [("away", "-0.25"), ("home", "0.25")])
        self.assertTrue(all(q["production_recommendation_allowed"] is False
                            and q["positive_ev_verified"] is False for q in quotes))

if __name__=="__main__":
    unittest.main()
