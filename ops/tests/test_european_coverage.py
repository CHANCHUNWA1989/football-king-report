import unittest
from ops.european_coverage import audit

class TestEuropeanCoverage(unittest.TestCase):
    def test_hold(self):
        result = audit()
        self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(len(result['competitions']), 8)
        self.assertFalse(result['live_odds_verified'])

if __name__ == '__main__':
    unittest.main()
