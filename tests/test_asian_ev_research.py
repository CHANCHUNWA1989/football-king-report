"""Unit tests for research-only quarter-line settlement."""
import unittest
from ops.asian_ev_research import asian_net, expected_value, PRODUCTION_RECOMMENDATIONS

class AsianEVTests(unittest.TestCase):
    def test_integer_total_push(self):
        self.assertEqual(asian_net(3, -3, 1.95), 0)
        self.assertAlmostEqual(asian_net(4, -3, 1.95), .95)
        self.assertEqual(asian_net(2, -3, 1.95), -1)

    def test_quarter_totals(self):
        self.assertAlmostEqual(asian_net(3, -2.75, 1.65), .325)
        self.assertAlmostEqual(asian_net(3, -3.25, 2.26), -.5)
        self.assertAlmostEqual(asian_net(2, -2.75, 1.65), -1)

    def test_handicap_quarter(self):
        self.assertAlmostEqual(asian_net(0, .25, 2), .5)
        self.assertAlmostEqual(asian_net(0, -.25, 2), -.5)
        self.assertAlmostEqual(asian_net(1, -.75, 2), .5)

    def test_expected_value(self):
        self.assertAlmostEqual(expected_value({2:.2,3:.3,4:.5}, -3, 1.95), .275)

    def test_fail_closed(self):
        for d in ({2:.6}, {2:-.1,3:1.1}):
            with self.assertRaises(ValueError):
                expected_value(d, -3, 1.95)
        with self.assertRaises(ValueError):
            asian_net(3, -3.1, 1.95)
        self.assertEqual(PRODUCTION_RECOMMENDATIONS, "DISABLED")

if __name__ == "__main__":
    unittest.main()
