import unittest
from ops.bookmaker_timestamp_gate import extract_verified_time_quotes

def fixture():
    return {"timestamp":"2026-11-06T12:00:00Z","data":[{
        "id":"synthetic-1","commence_time":"2026-11-06T13:00:00Z",
        "home_team":"A","away_team":"B",
        "bookmakers":[{"key":"synthetic_book","last_update":"2026-11-06T11:58:00Z",
            "markets":[{"key":"totals","last_update":"2026-11-06T11:58:00Z",
                        "outcomes":[{"name":"Over","point":2.5,"price":1.91}]}]}]}]}

class TimestampGateTests(unittest.TestCase):
    def test_valid_quote(self):
        q=extract_verified_time_quotes(fixture())
        self.assertEqual(len(q),1)
        self.assertTrue(q[0]["bookmaker_timestamp_checked"])
        self.assertFalse(q[0]["source_authenticity_verified"])
    def test_missing_bookmaker_timestamp(self):
        x=fixture();del x["data"][0]["bookmakers"][0]["last_update"]
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_future_bookmaker_timestamp(self):
        x=fixture();x["data"][0]["bookmakers"][0]["last_update"]="2026-11-06T12:01:00Z"
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_stale_bookmaker_timestamp(self):
        x=fixture();x["data"][0]["bookmakers"][0]["last_update"]="2026-11-06T10:00:00Z"
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_missing_market_timestamp(self):
        x=fixture();del x["data"][0]["bookmakers"][0]["markets"][0]["last_update"]
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_future_market_timestamp(self):
        x=fixture();x["data"][0]["bookmakers"][0]["markets"][0]["last_update"]="2026-11-06T12:01:00Z"
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_stale_market_timestamp(self):
        x=fixture();x["data"][0]["bookmakers"][0]["markets"][0]["last_update"]="2026-11-06T10:00:00Z"
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_invalid_age(self):
        with self.assertRaises(ValueError): extract_verified_time_quotes(fixture(),max_bookmaker_age_minutes=0)
    def test_duplicate_bookmaker_rejected(self):
        x=fixture()
        x["data"][0]["bookmakers"].append(dict(x["data"][0]["bookmakers"][0]))
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_duplicate_market_rejected(self):
        x=fixture()
        book=x["data"][0]["bookmakers"][0]
        book["markets"].append(dict(book["markets"][0]))
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_duplicate_event_id_rejected(self):
        x=fixture()
        x["data"].append(dict(x["data"][0]))
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_invalid_event_rejected(self):
        x=fixture()
        x["data"].append(None)
        with self.assertRaises(ValueError): extract_verified_time_quotes(x)
    def test_no_production(self):
        self.assertFalse(extract_verified_time_quotes(fixture())[0]["production_recommendation_allowed"])

if __name__=="__main__":
    unittest.main()
