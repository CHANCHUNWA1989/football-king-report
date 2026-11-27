import unittest
from ops.stress_repair_risk_overlay import flags,stats,evaluate
class RiskOverlayTests(unittest.TestCase):
    def test_draw_flag_keeps_probabilities(self):
        p=[.40,.30,.30]
        r=flags(p,.12,.55)
        self.assertTrue(r["draw_risk"]);self.assertFalse(r["high_confidence_research"])
        self.assertEqual(r["probability"],p)
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_no_threshold_no_flag(self):
        r=flags([.6,.25,.15],None,None)
        self.assertIsNone(r["draw_risk"]);self.assertIsNone(r["high_confidence_research"])
    def test_invalid_probability(self):
        with self.assertRaises(ValueError):flags([.9,.9,.1],.12,.55)
    def test_no_unverified_anchor(self):
        with self.assertRaisesRegex(ValueError,"ANCHOR_CONTRACT"):evaluate({})
