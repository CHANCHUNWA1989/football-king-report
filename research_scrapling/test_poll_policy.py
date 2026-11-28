import unittest
from concurrent.futures import ThreadPoolExecutor
from poll_policy import PollPolicy


class PollTests(unittest.TestCase):
    def setUp(self):
        self.p = PollPolicy(["a", "b"])

    def complete_revision(self):
        lease = self.p.reserve("a", 0)
        self.assertEqual(self.p.finish("a", lease, 1, 200, "r1"), "RESEARCH_PAYLOAD_PENDING")

    def test_budget(self):
        self.complete_revision()
        self.assertIsNone(self.p.reserve("a", 60))
        self.assertEqual(self.p.reserve("a", 61)[1], "payload")

    def test_concurrent_reservation(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: self.p.reserve("a", 0), range(32)))
        self.assertEqual(sum(x is not None for x in results), 1)

    def test_independent_scopes(self):
        self.assertIsNotNone(self.p.reserve("a", 0))
        self.assertIsNotNone(self.p.reserve("b", 0))

    def test_revision_not_committed_before_payload(self):
        self.complete_revision()
        self.assertIsNone(self.p.snapshot("a")["cached_revision"])

    def test_unchanged_not_fresh(self):
        self.complete_revision()
        lease = self.p.reserve("a", 61)
        self.p.finish("a", lease, 62, 200, "r1")
        lease = self.p.reserve("a", 122)
        self.assertEqual(self.p.finish("a", lease, 123, 200, "r1"), "UNCHANGED_NOT_FRESH_EVIDENCE")

    def test_payload_mismatch(self):
        self.complete_revision()
        lease = self.p.reserve("a", 61)
        self.assertEqual(self.p.finish("a", lease, 62, 200, "r2"), "HOLD_ERROR")
        self.assertIsNone(self.p.snapshot("a")["cached_revision"])
        self.assertIsNone(self.p.snapshot("a")["pending_revision"])
        self.assertEqual(self.p.reserve("a", 182)[1], "revision")

    def test_retry_after(self):
        lease = self.p.reserve("a", 0)
        self.p.finish("a", lease, 1, 429, retry_after=7200)
        self.assertIsNone(self.p.reserve("a", 7200))
        self.assertIsNotNone(self.p.reserve("a", 7201))

    def test_exponential_backoff(self):
        lease = self.p.reserve("a", 0)
        self.p.finish("a", lease, 1, 503)
        self.assertEqual(self.p.snapshot("a")["next_eligible"], 121)
        lease = self.p.reserve("a", 121)
        self.p.finish("a", lease, 122, 503)
        self.assertEqual(self.p.snapshot("a")["next_eligible"], 362)

    def test_access_denied_halts(self):
        lease = self.p.reserve("a", 0)
        self.p.finish("a", lease, 1, 403)
        self.assertIsNone(self.p.reserve("a", 100000))

    def test_clock_rollback(self):
        self.p.reserve("a", 10)
        with self.assertRaises(ValueError):
            self.p.reserve("b", 9)

    def test_duplicate_completion(self):
        lease = self.p.reserve("a", 0)
        self.p.finish("a", lease, 1, 200, "r1")
        with self.assertRaises(ValueError):
            self.p.finish("a", lease, 2, 200, "r1")

    def test_safety(self):
        self.complete_revision()
        s = self.p.snapshot("a")
        self.assertEqual((s["status"], s["live_trading"], s["production_recommendations"]), ("HOLD", "DISABLED", "DISABLED"))
        self.assertFalse(s["model_input_allowed"])
        self.assertFalse(s["network_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
