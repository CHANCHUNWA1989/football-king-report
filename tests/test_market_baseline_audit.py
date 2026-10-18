import unittest
from research_quality.market_baseline_audit import compare

class TestMarket(unittest.TestCase):
    def test_empty(self):
        self.assertIsNone(compare([])['market_minus_model_brier'])
    def test_equal(self):
        p = [0.5, 0.3, 0.2]
        self.assertEqual(compare([{'p':p,'m':p,'y':0}])['market_minus_model_brier'],0)
