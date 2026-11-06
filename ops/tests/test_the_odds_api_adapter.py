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

if __name__=="__main__":
    unittest.main()
