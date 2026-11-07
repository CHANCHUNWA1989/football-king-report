import unittest
from ops.snapshot_validation import validate_snapshot, validate_dataset

def good():
    return dict(event_id="synthetic-001",competition="Synthetic",kickoff_at="2026-11-06T20:00:00+08:00",
                captured_at="2026-11-06T19:45:00+08:00",forecast_created_at="2026-11-06T19:30:00+08:00",
                bookmaker="TEST_ONLY",source_url="https://example.invalid/fixture",
                market="total",side="under",line="2.5",odds="1.87",home_goals=0,away_goals=0,
                model_version="synthetic",score_probabilities={"0-0":"0.6","1-1":"0.4"})

class SnapshotTests(unittest.TestCase):
    def test_valid_is_unverified(self):
        r=validate_snapshot(good())
        self.assertEqual(r["evidence_status"],"UNVERIFIED")
        self.assertFalse(r["positive_ev_verified"])
        self.assertFalse(r["production_recommendation_allowed"])
    def test_missing_source(self):
        x=good();del x["source_url"]
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_postkickoff_quote(self):
        x=good();x["captured_at"]=x["kickoff_at"]
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_future_forecast(self):
        x=good();x["forecast_created_at"]=x["kickoff_at"]
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_stale_quote(self):
        x=good();x["captured_at"]="2026-11-06T18:00:00+08:00"
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_invalid_probabilities(self):
        x=good();x["score_probabilities"]={"0-0":"0.8"}
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_negative_probabilities(self):
        x=good();x["score_probabilities"]={"0-0":"1.1","1-1":"-0.1"}
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_invalid_market(self):
        x=good();x["market"]="moneyline"
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_invalid_line(self):
        x=good();x["line"]="2.3"
        with self.assertRaises(ValueError): validate_snapshot(x)
    def test_negative_total_lines_rejected(self):
        for side in ("over", "under"):
            for line in ("-0.25", "-0.5", "-0.75", "-1.0"):
                x=good();x.update(side=side,line=line)
                with self.subTest(side=side, line=line), self.assertRaises(ValueError):
                    validate_snapshot(x)
    def test_nonnegative_total_lines_preserve_research_gates(self):
        for side in ("over", "under"):
            for line in ("0", "0.25", "0.5", "0.75"):
                x=good();x.update(side=side,line=line)
                with self.subTest(side=side, line=line):
                    result=validate_snapshot(x)
                    self.assertEqual(result["line"],line)
                    self.assertFalse(result["positive_ev_verified"])
                    self.assertFalse(result["production_recommendation_allowed"])
    def test_negative_handicap_lines_remain_valid(self):
        for side in ("home", "away"):
            for line in ("-0.25", "-1.0"):
                x=good();x.update(market="handicap",side=side,line=line)
                with self.subTest(side=side, line=line):
                    result=validate_snapshot(x)
                    self.assertEqual((result["market"],result["side"],result["line"]),
                                     ("handicap",side,line))
                    self.assertFalse(result["production_recommendation_allowed"])
    def test_duplicate(self):
        with self.assertRaises(ValueError): validate_dataset([good(),good()])
    def test_equivalent_snapshot_identity_rejected(self):
        for changes in ({"line": "2.50"},
                        {"captured_at": "2026-11-06T11:45:00Z"},
                        {"line": "2.50", "captured_at": "2026-11-06T11:45:00Z", "odds": "2.1"}):
            with self.subTest(changes=changes):
                first=good()
                with self.assertRaisesRegex(ValueError, "duplicate market snapshot"):
                    validate_dataset([first,dict(first, **changes)])
    def test_distinct_snapshot_identities_preserve_raw_fields(self):
        for changes in ({"line": "2.75"}, {"bookmaker": "OTHER_TEST"},
                        {"side": "over"}, {"captured_at": "2026-11-06T19:46:00+08:00"}):
            with self.subTest(changes=changes):
                first=good()
                second=dict(first, **changes)
                rows=validate_dataset([first,second])
                self.assertEqual(len(rows),2)
                for key in ("line", "captured_at", "bookmaker", "side"):
                    self.assertEqual(rows[1][key],second[key])
                self.assertTrue(all(row["production_recommendation_allowed"] is False
                                    and row["positive_ev_verified"] is False for row in rows))
    def test_dataset_one(self):
        self.assertEqual(len(validate_dataset([good()])),1)
    def test_naive_datetime(self):
        x=good();x["captured_at"]="2026-11-06T19:45:00"
        with self.assertRaises(ValueError): validate_snapshot(x)

if __name__=="__main__":
    unittest.main()
