import unittest
from shared.source_freshness import check_source

class FreshnessTests(unittest.TestCase):
    def test_fresh(self):
        r = check_source("fixture", "2026-10-17T10:00:00+08:00", "2026-10-17T10:01:00+08:00")
        self.assertTrue(r["verified_freshness"])
        self.assertFalse(r["live_execution_allowed"])
    def test_stale(self):
        self.assertIn("STALE_SOURCE", check_source("fixture", "2026-10-17T10:00:00+08:00", "2026-10-17T10:10:00+08:00")["reasons"])
    def test_future(self):
        self.assertIn("FUTURE_SOURCE_TIMESTAMP", check_source("fixture", "2026-10-17T10:02:00+08:00", "2026-10-17T10:00:00+08:00")["reasons"])
    def test_naive_time(self):
        with self.assertRaises(ValueError):
            check_source("fixture", "2026-10-17T10:00:00", "2026-10-17T10:01:00+08:00")
    def test_missing_source(self):
        with self.assertRaises(ValueError):
            check_source("", "2026-10-17T10:00:00+08:00", "2026-10-17T10:01:00+08:00")
    def test_invalid_age(self):
        with self.assertRaises(ValueError):
            check_source("fixture", "2026-10-17T10:00:00+08:00", "2026-10-17T10:01:00+08:00", 0)

if __name__ == "__main__":
    unittest.main()
