import unittest
from ops.frozen_forecast_join import join_frozen_forecasts, join_historical_envelope

def sample():
    q=[dict(event_id="synthetic-1",bookmaker="test",market="total",side="over",line="2.5",odds="1.9",bookmaker_timestamp_checked=True,production_recommendation_allowed=False,captured_at="2026-11-06T12:00:00Z",kickoff_at="2026-11-06T13:00:00Z")]
    f=[dict(event_id="synthetic-1",created_at="2026-11-06T11:00:00Z",training_data_cutoff_at="2026-11-05T00:00:00Z",model_version="test",model_artifact_sha256="a"*64,score_probabilities={"0-0":"0.6","1-1":"0.4"})]
    r=[dict(event_id="synthetic-1",home_goals=0,away_goals=0)]
    return q,f,r

class FrozenJoinTests(unittest.TestCase):
    def test_valid_join_still_unverified(self):
        result=join_frozen_forecasts(*sample())
        self.assertEqual(len(result),1)
        self.assertFalse(result[0]["out_of_sample_verified"])
        self.assertFalse(result[0]["production_recommendation_allowed"])
    def test_forecast_after_quote(self):
        q,f,r=sample();f[0]["created_at"]="2026-11-06T12:01:00Z"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_training_cutoff_after_forecast(self):
        q,f,r=sample();f[0]["training_data_cutoff_at"]="2026-11-06T11:01:00Z"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_missing_forecast(self):
        q,f,r=sample()
        with self.assertRaises(ValueError): join_frozen_forecasts(q,[],r)
    def test_missing_result(self):
        q,f,r=sample()
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,[])
    def test_duplicate_forecast(self):
        q,f,r=sample()
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f+f,r)
    def test_duplicate_quote(self):
        q,f,r=sample()
        with self.assertRaises(ValueError): join_frozen_forecasts(q+q,f,r)
    def test_missing_model_hash(self):
        q,f,r=sample();f[0]["model_artifact_sha256"]=""
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_invalid_probability(self):
        q,f,r=sample();f[0]["score_probabilities"]={"0-0":"1.2"}
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_missing_freshness_gate(self):
        q,f,r=sample();del q[0]["bookmaker_timestamp_checked"]
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_bad_market(self):
        q,f,r=sample();q[0]["market"]="h2h"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_bad_odds(self):
        q,f,r=sample();q[0]["odds"]="1"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_invalid_line(self):
        q,f,r=sample();q[0]["line"]="2.3"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_raw_envelope_timestamp_gate(self):
        q,f,r=sample()
        envelope={"timestamp":"2026-11-06T12:00:00Z","data":[{
            "id":"synthetic-1","commence_time":"2026-11-06T13:00:00Z",
            "home_team":"A","away_team":"B",
            "bookmakers":[{"key":"test","last_update":"2026-11-06T11:59:00Z",
                "markets":[{"key":"totals","last_update":"2026-11-06T11:59:00Z",
                    "outcomes":[{"name":"Over","point":2.5,"price":1.9}]}]}]}]}
        self.assertEqual(len(join_historical_envelope(envelope,f,r)),1)
        del envelope["data"][0]["bookmakers"][0]["last_update"]
        with self.assertRaises(ValueError):
            join_historical_envelope(envelope,f,r)
    def test_negative_score(self):
        q,f,r=sample();r[0]["home_goals"]=-1
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)

if __name__=="__main__":
    unittest.main()
