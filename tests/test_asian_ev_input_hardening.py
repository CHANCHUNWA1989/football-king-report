"""Research-only regression tests for malformed Asian EV inputs."""
import unittest
from ops.asian_ev_research import asian_net, expected_value

class AsianEVInputHardeningTests(unittest.TestCase):
    def test_reject_boolean_odds(self):
        with self.assertRaises(ValueError):
            asian_net(1, -0.5, True)

    def test_reject_boolean_line(self):
        with self.assertRaises(ValueError):
            asian_net(1, True, 1.95)

    def test_reject_boolean_probability(self):
        with self.assertRaises(ValueError):
            expected_value({1: True}, -0.5, 1.95)

    def test_quarter_line_symmetry_and_push(self):
        self.assertAlmostEqual(asian_net(-1, 1.25, 2.0), 0.5)
        self.assertAlmostEqual(asian_net(1, -1.25, 2.0), -0.5)
        self.assertEqual(asian_net(-1, 1.0, 2.0), 0.0)

    def test_reject_boolean_margin_and_distribution_key(self):
        with self.assertRaises(ValueError):
            asian_net(True, -0.5, 1.95)
        with self.assertRaises(ValueError):
            expected_value({True: 1.0}, -0.5, 1.95)

    def test_reject_nonfinite_inputs(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    asian_net(1, -0.5, value)
                with self.assertRaises(ValueError):
                    expected_value({1: value}, -0.5, 1.95)

if __name__ == "__main__":
    unittest.main()
