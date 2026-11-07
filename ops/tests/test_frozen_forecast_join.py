import copy
import unittest
from ops.frozen_forecast_join import join_frozen_forecasts, join_historical_envelope

def sample():
    q=[dict(event_source="the_odds_api_v4",event_id="synthetic-1",bookmaker="test",market="total",side="over",line="2.5",odds="1.9",bookmaker_timestamp_checked=True,bookmaker_last_update="2026-11-06T11:59:00Z",market_last_update="2026-11-06T11:59:00Z",production_recommendation_allowed=False,captured_at="2026-11-06T12:00:00Z",kickoff_at="2026-11-06T13:00:00Z")]
    f=[dict(event_source="the_odds_api_v4",event_id="synthetic-1",created_at="2026-11-06T11:00:00Z",training_data_cutoff_at="2026-11-05T00:00:00Z",model_version="test",model_artifact_sha256="a"*64,score_probabilities={"0-0":"0.6","1-1":"0.4"})]
    r=[dict(event_source="the_odds_api_v4",event_id="synthetic-1",home_goals=0,away_goals=0)]
    return q,f,r

class FrozenJoinTests(unittest.TestCase):
    def test_cross_provider_native_id_collision_cannot_join(self):
        for role in ("forecast", "result"):
            for self_approved_mapping in (False, True):
                with self.subTest(role=role, self_approved_mapping=self_approved_mapping):
                    q, f, r = sample()
                    for row in (q[0], f[0], r[0]):
                        row.update(event_source="provider-a", event_id="123",
                                   home_team="Match A Home", away_team="Match A Away")
                    other = f[0] if role == "forecast" else r[0]
                    other.update(event_source="provider-b", home_team="Match B Home",
                                 away_team="Match B Away")
                    if self_approved_mapping:
                        other["identity_mapping"] = {"independently_verified": True,
                                                     "target_event_id": "123"}
                    with self.assertRaises(ValueError):
                        join_frozen_forecasts(q, f, r)

    def test_explicit_event_namespace_required_on_all_inputs(self):
        for role in range(3):
            for source in (None, "", " ", True):
                with self.subTest(role=role, source=source):
                    rows = sample()
                    if source is None:
                        rows[role][0].pop("event_source")
                    else:
                        rows[role][0]["event_source"] = source
                    with self.assertRaises(ValueError):
                        join_frozen_forecasts(*rows)

    def test_same_native_id_can_coexist_in_distinct_provider_namespaces(self):
        q, f, r = [], [], []
        for source, goals in (("provider-a", 0), ("provider-b", 1)):
            one = sample()
            for collection in one:
                collection[0].update(event_source=source, event_id="123")
            one[1][0]["model_version"] = "model-" + source
            one[2][0]["home_goals"] = goals
            for target, collection in zip((q, f, r), one):
                target.extend(collection)
        f.reverse()
        r.reverse()
        original = copy.deepcopy((q, f, r))
        joined = join_frozen_forecasts(q, f, r)
        self.assertEqual((q, f, r), original)
        self.assertEqual([row["event_source"] for row in joined], ["provider-a", "provider-b"])
        self.assertEqual([row["event_id"] for row in joined], ["123", "123"])
        self.assertEqual([row["model_version"] for row in joined],
                         ["model-provider-a", "model-provider-b"])
        self.assertEqual([row["home_goals"] for row in joined], [0, 1])
        self.assertTrue(all(row["positive_ev_verified"] is False
                            and row["production_recommendation_allowed"] is False
                            for row in joined))

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
    def test_forged_freshness_flag_missing_raw_timestamp(self):
        q,f,r=sample();del q[0]["bookmaker_last_update"]
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_stale_raw_timestamp_even_with_flag(self):
        q,f,r=sample();q[0]["market_last_update"]="2026-11-06T10:00:00Z"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_future_raw_timestamp_even_with_flag(self):
        q,f,r=sample();q[0]["market_last_update"]="2026-11-06T12:01:00Z"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
    def test_custom_age_window_applies_to_direct_join(self):
        q,f,r=sample()
        q[0]["bookmaker_last_update"]="2026-11-06T11:20:00Z"
        q[0]["market_last_update"]="2026-11-06T11:20:00Z"
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)
        self.assertEqual(len(join_frozen_forecasts(q,f,r,max_bookmaker_age_minutes=45)),1)
    def test_invalid_custom_age(self):
        q,f,r=sample()
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r,max_bookmaker_age_minutes=True)
    def test_negative_score(self):
        q,f,r=sample();r[0]["home_goals"]=-1
        with self.assertRaises(ValueError): join_frozen_forecasts(q,f,r)

if __name__=="__main__":
    unittest.main()
