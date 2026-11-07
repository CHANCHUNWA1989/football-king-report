import unittest
from datetime import datetime
from ops.private_upstream_soccerdata_adapter import adapt_matchhistory_frame, read_upstream_matchhistory


class SoccerdataAdapterTests(unittest.TestCase):
    def setUp(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not installed")
        self.pd = pd
        self.frame = pd.DataFrame([{"date": datetime(2026, 1, 1, 15, 0),
                                    "home_team": "Home", "away_team": "Away",
                                    "FTHG": 2, "FTAG": 1}])

    def test_settled_result_without_false_utc_claim(self):
        result = adapt_matchhistory_frame(self.frame)
        self.assertEqual(result["records"][0]["outcome"], "H")
        self.assertIsNone(result["records"][0]["kickoff_utc"])
        self.assertFalse(result["point_in_time_backtest_ready"])

    def test_invalid_score_rejected(self):
        self.frame.loc[0, "FTHG"] = -1
        with self.assertRaises(ValueError):
            adapt_matchhistory_frame(self.frame)

    def test_aware_datetime_rejected(self):
        self.frame["date"] = self.pd.Series([self.pd.Timestamp("2026-01-01T15:00:00Z")], dtype="object")
        with self.assertRaises(ValueError):
            adapt_matchhistory_frame(self.frame)

    def test_upstream_constructor_is_available(self):
        try:
            import soccerdata
        except ImportError:
            self.skipTest("optional soccerdata not installed")
        # Only instantiate; do not invoke any external source or network.
        reader = read_upstream_matchhistory(leagues=["ENG-Premier League"], seasons=["2526"])
        self.assertTrue(hasattr(reader, "read_games"))


if __name__ == "__main__":
    unittest.main()
