import unittest
from datetime import datetime, timedelta, timezone
from ops.global_full_slate import build

NOW = datetime(2026, 11, 26, 10, tzinfo=timezone.utc)
KO = (NOW + timedelta(hours=2)).isoformat()

class FullSlateTests(unittest.TestCase):
    def build(self, rows, world=None, shadow=None):
        return build({"fixtures":{"matches":rows}}, world, shadow, None,
                     now=NOW, start=NOW-timedelta(hours=10), end=NOW+timedelta(days=1))

    def test_retains_unqualified_and_duplicate_accounting(self):
        row = dict(league="cup", home="A", away="B", event_id="1",
                   kickoff_utc=KO, status="SCHEDULED")
        result = self.build([row, row, {"home":"C"}, None])
        self.assertEqual(result["counts"]["input_rows"], 4)
        self.assertEqual(result["counts"]["duplicate_observations"], 1)
        self.assertEqual(len(result["rows"]), 3)
        self.assertFalse(result["global_coverage_complete"])
        self.assertIsNone(result["unique_global_match_count"])
        self.assertEqual(result["qualified_recommendations"], 0)

    def test_two_publishers_and_conflict_are_not_falsely_merged(self):
        common = dict(home="A", away="B", provider_event_id="1", kickoff_utc=KO,
                      status="SCHEDULED", captured_utc=NOW.isoformat())
        world = dict(production_recommendations="DISABLED", collected_utc=NOW.isoformat(),
                     leagues=[dict(id="cup", fixture_observations=[
                         dict(common, provider="one"), dict(common, provider="two"),
                         dict(common, provider="one", status="POSTPONED")])])
        result = self.build([], world)
        self.assertEqual(len(result["rows"]), 3)
        self.assertTrue(all(x["status"] == "HOLD" for x in result["rows"]))

    def test_stale_unsafe_and_missing_model_do_not_link(self):
        row = dict(league="cup", home="A", away="B", event_id="1",
                   kickoff_utc=KO, status="SCHEDULED")
        pred = dict(row, prediction_utc=NOW.isoformat(), production_recommendations="DISABLED")
        model = dict(as_of_utc=NOW.isoformat(), predictions=[pred], production_recommendations="DISABLED")
        self.assertTrue(self.build([row], shadow=model)["rows"][0]["exact_core_model_reference"])
        model["as_of_utc"] = (NOW-timedelta(days=1)).isoformat()
        self.assertFalse(self.build([row], shadow=model)["rows"][0]["exact_core_model_reference"])
        row["kickoff_utc"] = "2026-11-26T12:00:00"
        self.assertIn("MISSING_OR_INVALID_KICKOFF", self.build([row])["rows"][0]["reasons"])

    def test_corrected_scores_preserved_and_references_quarantined(self):
        row=dict(league="cup",home="A",away="B",event_id="1",kickoff_utc=KO,status="SCHEDULED")
        pred=dict(row,prediction_utc=NOW.isoformat(),production_recommendations="DISABLED")
        model=dict(as_of_utc=NOW.isoformat(),predictions=[pred],production_recommendations="DISABLED")
        r=self.build([row,dict(row,score_ft=[1,0]),dict(row,score_ft=[2,0])],shadow=model)
        self.assertEqual(r["counts"]["retained_observations"],3)
        self.assertEqual(r["counts"]["duplicate_observations"],0)
        self.assertEqual(r["counts"]["conflicting_native_id_groups"],1)
        self.assertEqual(r["counts"]["conflicting_observations"],3)
        self.assertEqual(r["counts"]["exact_core_model_reference_observations"],0)
        self.assertEqual([x["observed_score_ft_unverified"] for x in r["rows"]],[None,[1,0],[2,0]])
        self.assertTrue(all("NATIVE_ID_OBSERVATION_CONFLICT" in x["reasons"] for x in r["rows"]))

    def test_distinct_capture_times_not_conflicts_and_exact_repeats_dedup(self):
        row=dict(league="cup",home="A",away="B",event_id="1",kickoff_utc=KO,status="SCHEDULED",
                 captured_utc=NOW.isoformat())
        earlier=dict(row,captured_utc=(NOW-timedelta(minutes=1)).isoformat())
        r=self.build([row,earlier,row])
        self.assertEqual(r["counts"]["retained_observations"],2)
        self.assertEqual(r["counts"]["duplicate_observations"],1)
        self.assertEqual(r["counts"]["conflicting_native_id_groups"],0)

    def test_invalid_score_and_bad_clock_not_collapsed(self):
        row=dict(league="cup",home="A",away="B",event_id="1",kickoff_utc=KO,status="SCHEDULED",
                 captured_utc="bad",score_ft=[True,0])
        r=self.build([row,row])
        self.assertEqual(r["counts"]["retained_observations"],2)
        self.assertEqual(r["counts"]["duplicate_observations"],0)
        self.assertTrue(all("INVALID_SCORE_OBSERVATION" in x["reasons"] for x in r["rows"]))
        self.assertTrue(all(x["observed_score_ft_unverified"] is None for x in r["rows"]))

    def test_postponed_row_never_links_to_prematch_model(self):
        row=dict(league="cup",home="A",away="B",event_id="1",kickoff_utc=KO,status="SCHEDULED")
        pred=dict(row,prediction_utc=NOW.isoformat(),production_recommendations="DISABLED")
        model=dict(as_of_utc=NOW.isoformat(),predictions=[pred],production_recommendations="DISABLED")
        r=self.build([dict(row,status="POSTPONED")],shadow=model)
        self.assertFalse(r["rows"][0]["exact_core_model_reference"])

    def test_different_capture_and_score_states_retained(self):
        common = dict(home="A", away="B", provider_event_id="1", kickoff_utc=KO,
                      status="SCHEDULED", captured_utc=NOW.isoformat(), provider="one")
        world = dict(production_recommendations="DISABLED", collected_utc=NOW.isoformat(),
                     leagues=[dict(id="cup", fixture_observations=[
                         common, dict(common), dict(common, captured_utc=(NOW-timedelta(days=1)).isoformat()),
                         dict(common, score_ft=[1,0])])])
        result = self.build([], world)
        self.assertEqual(result["counts"]["duplicate_observations"], 1)
        self.assertEqual(len(result["rows"]), 3)
        self.assertTrue(any("OBSERVATION_TIME_UNVERIFIED_OR_STALE" in x["reasons"] for x in result["rows"]))
        self.assertTrue(any("NOT_CONFIRMED_FUTURE_PREMATCH" in x["reasons"] for x in result["rows"]))
        self.assertEqual(result["qualified_recommendations"], 0)

if __name__ == "__main__":
    unittest.main()
