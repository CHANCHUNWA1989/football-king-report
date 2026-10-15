import unittest
from settlement_gap import settlement_gap

class SettlementGapTests(unittest.TestCase):
    def test_zero_verified(self):
        report=settlement_gap(0)
        self.assertEqual(report["remaining"],300)
        self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_partial_progress(self):
        self.assertEqual(settlement_gap(120)["remaining"],180)

    def test_invalid_count(self):
        with self.assertRaises(ValueError):
            settlement_gap(-1)

if __name__=="__main__":
    unittest.main()
