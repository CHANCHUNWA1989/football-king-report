import unittest
from test_fourway_calibration_diagnostic import FourWayCalibrationTests
from fourway_calibration_diagnostic import weight_sensitivity
class LeagueWeightTests(unittest.TestCase):
    row=FourWayCalibrationTests.row
    run_rows=FourWayCalibrationTests.run_rows
    def test_same_cases_and_market_control(self):
        rows=[self.row(0,league="epl"),self.row(1,league="laliga"),self.row(2,league="epl")]
        r=self.run_rows(rows)
        self.assertEqual(sum(v["n"] for v in r["by_league_descriptive"].values()),3)
        for v in r["by_league_descriptive"].values():
            self.assertTrue(v["below_40_cases"])
            self.assertFalse(v["independent_validation"])
        s=r["fixed_weight_sensitivity"]
        self.assertIsNone(s["selected_weight"])
        self.assertFalse(s["promotion_allowed"])
        self.assertAlmostEqual(s["weights"][0]["log_loss"],r["models"]["market"]["log_loss"])
        self.assertAlmostEqual(s["weights"][-1]["brier"],r["models"]["A"]["brier"])
    def test_empty_no_weight_selected(self):
        self.assertEqual(weight_sensitivity([])["weights"],[])
