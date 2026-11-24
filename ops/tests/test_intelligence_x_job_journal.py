import hashlib
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from intelligence_x_job_journal import claim, finish, stop


class JobJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'journal.sqlite'
        self.job = 'a' * 64

    def test_duplicate_and_restart(self):
        a = claim(self.path, self.job, now=100)
        self.assertIsNone(claim(self.path, self.job, now=159))
        b = claim(self.path, self.job, now=160)
        self.assertEqual(b['attempt'], 2)
        self.assertNotEqual(a['token'], b['token'])
        self.assertFalse(finish(self.path, self.job, token=a['token'], now=161))
        self.assertTrue(finish(self.path, self.job, token=b['token'], now=161))
        self.assertIsNone(claim(self.path, self.job, now=1000))

    def test_timeout_and_attempt_limit(self):
        for i in range(3):
            a = claim(self.path, self.job, now=100 + i*60)
            self.assertEqual(a['attempt'], i+1)
            self.assertFalse(finish(self.path, self.job, token=a['token'], now=160+i*60))
        self.assertIsNone(claim(self.path, self.job, now=280))
        self.assertIsNone(claim(self.path, self.job, now=1000))

    def test_stop_revokes_lease(self):
        a = claim(self.path, self.job, now=100)
        self.assertTrue(stop(self.path, self.job, now=101))
        self.assertFalse(finish(self.path, self.job, token=a['token'], now=102))
        self.assertIsNone(claim(self.path, self.job, now=1000))

    def test_stop_before_start(self):
        self.assertTrue(stop(self.path, self.job, now=100))
        self.assertIsNone(claim(self.path, self.job, now=101))

    def test_clock_rollback_and_invalid_inputs(self):
        claim(self.path, self.job, now=100)
        with self.assertRaisesRegex(ValueError, 'CLOCK_ROLLBACK'):
            claim(self.path, self.job, now=99)
        for job, now in [('bad', 100), (self.job, True), (self.job, -1)]:
            with self.assertRaises(ValueError):
                claim(self.path, job, now=now)

    def test_expired_observation_cannot_be_rolled_back(self):
        a = claim(self.path, self.job, now=100)
        self.assertFalse(finish(self.path, self.job, token=a['token'], now=160))
        with self.assertRaisesRegex(ValueError, 'CLOCK_ROLLBACK'):
            finish(self.path, self.job, token=a['token'], now=159)

    def test_concurrent_claim(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: claim(self.path, self.job, now=100), range(32)))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_1000_synthetic_recoveries(self):
        for i in range(1000):
            job = hashlib.sha256(str(i).encode()).hexdigest()
            a = claim(self.path, job, now=100)
            b = claim(self.path, job, now=160)
            self.assertFalse(finish(self.path, job, token=a['token'], now=161))
            self.assertTrue(finish(self.path, job, token=b['token'], now=161))
            self.assertIsNone(claim(self.path, job, now=162))
            self.assertEqual(b['status'], 'HOLD')
            self.assertEqual(b['production_recommendations'], 'DISABLED')


if __name__ == '__main__':
    unittest.main()
