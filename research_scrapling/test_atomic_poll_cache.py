from contextlib import closing
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from atomic_poll_cache import AtomicPollCache


class AtomicTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'atomic.db'
        self.p = AtomicPollCache.initialize(self.path, ['a'])

    def lease(self):
        self.p.finish('a', self.p.reserve('a', 100), 101, 200, 'v1')
        return self.p.reserve('a', 161)

    def commit(self):
        return self.p.finish_payload('a', self.lease(), 162, 200, 'v1', b'fixture')

    def test_commit_restart(self):
        self.assertEqual(self.commit(), 'RESEARCH_CACHE_REVISION_COMMITTED')
        p = AtomicPollCache(self.path)
        self.assertEqual(p.snapshot('a')['cached_revision'], 'v1')
        self.assertEqual(p.get('a', 163)['body'], b'fixture')

    def test_write_failure_rolls_back(self):
        lease = self.lease()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON payload BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.Error):
            self.p.finish_payload('a', lease, 162, 200, 'v1', b'fixture')
        self.assertTrue(self.p.snapshot('a')['in_flight'])
        self.assertIsNone(self.p.snapshot('a')['cached_revision'])
        with closing(sqlite3.connect(self.path)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM payload').fetchone()[0], 0)

    def test_no_payload_bypass(self):
        lease = self.lease()
        with self.assertRaises(ValueError):
            self.p.finish('a', lease, 162, 200, 'v1')
        self.assertTrue(self.p.snapshot('a')['in_flight'])

    def test_invalid_body(self):
        lease = self.lease()
        with self.assertRaises(ValueError):
            self.p.finish_payload('a', lease, 162, 200, 'v1', b'')
        self.assertTrue(self.p.snapshot('a')['in_flight'])

    def test_mismatch(self):
        self.assertEqual(self.p.finish_payload('a', self.lease(), 162, 200, 'v2', b'fixture'), 'HOLD_ERROR')
        self.assertIsNone(self.p.get('a', 163)['body'])

    def test_expiry(self):
        self.commit()
        self.assertIsNotNone(self.p.get('a', 462)['body'])
        self.assertIsNone(self.p.get('a', 463)['body'])

    def test_corruption(self):
        self.commit()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('DELETE FROM payload')
        with self.assertRaises(ValueError):
            self.p.reserve('a', 222)

    def test_unchanged_does_not_refresh(self):
        self.commit()
        self.p.finish('a', self.p.reserve('a', 400), 401, 200, 'v1')
        self.assertIsNone(self.p.get('a', 463)['body'])

    def test_pending_hides_old(self):
        self.commit()
        self.p.finish('a', self.p.reserve('a', 222), 223, 200, 'v2')
        self.assertIsNone(self.p.get('a', 224)['body'])

    def test_repeated_connections_release(self):
        import gc
        import warnings
        from persistent_poll_policy import PersistentPollPolicy
        from research_cache import ResearchCache
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always', ResourceWarning)
            for i in range(32):
                root = self.path.parent
                poll = PersistentPollPolicy.initialize(root / f'poll-{i}.db', ['a'])
                cache = ResearchCache.initialize(root / f'cache-{i}.db', ['a'])
                atomic = AtomicPollCache.initialize(root / f'atomic-{i}.db', ['a'])
                for _ in range(8):
                    poll.snapshot('a')
                    cache.get('a', 'v1', 100)
                    atomic.get('a', 100)
            gc.collect()
        self.assertEqual([str(w.message) for w in observed if issubclass(w.category, ResourceWarning)], [])

    def test_safety(self):
        self.commit()
        r = self.p.get('a', 163)
        self.assertEqual((r['status'], r['live_trading'], r['production_recommendations']), ('HOLD','DISABLED','DISABLED'))
        self.assertFalse(r['model_input_allowed'])
        self.assertFalse(r['fresh_evidence'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
