from contextlib import closing
import sqlite3
import subprocess
import sys
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

    def child(self, code):
        r = subprocess.run([sys.executable, '-c', code, str(self.path)],
                           cwd=Path(__file__).resolve().parent,
                           capture_output=True, timeout=15)
        self.assertEqual(r.returncode, 77, r.stderr.decode(errors='replace'))

    def test_abrupt_exit_after_reservation(self):
        self.child("import os,sys; from atomic_poll_cache import AtomicPollCache; "
                   "p=AtomicPollCache(sys.argv[1]); assert p.reserve('a',100); os._exit(77)")
        self.assertTrue(self.p.snapshot('a')['in_flight'])
        self.assertIsNone(self.p.reserve('a', 10000))

    def test_abrupt_exit_inside_payload_transaction(self):
        lease = self.lease()
        self.child("import os,sys\nfrom atomic_poll_cache import AtomicPollCache\n"
                   "class CrashConnection:\n"
                   "    def __init__(self, db): self.db=db\n"
                   "    def __getattr__(self, name): return getattr(self.db,name)\n"
                   "    def execute(self, sql, *args):\n"
                   "        result=self.db.execute(sql,*args)\n"
                   "        if sql.startswith('INSERT INTO payload '): os._exit(77)\n"
                   "        return result\n"
                   "class CrashStore(AtomicPollCache):\n"
                   "    def _connect(self): return CrashConnection(super()._connect())\n"
                   f"CrashStore(sys.argv[1]).finish_payload('a',{lease!r},162,200,'v1',b'fixture')")
        self.assertTrue(self.p.snapshot('a')['in_flight'])
        self.assertIsNone(self.p.snapshot('a')['cached_revision'])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM payload').fetchone()[0], 0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_abrupt_exit_after_commit(self):
        lease = self.lease()
        self.child("import os,sys; from atomic_poll_cache import AtomicPollCache; "
                   f"p=AtomicPollCache(sys.argv[1]); assert p.finish_payload('a',{lease!r},162,200,'v1',b'fixture')=='RESEARCH_CACHE_REVISION_COMMITTED'; os._exit(77)")
        self.assertFalse(self.p.snapshot('a')['in_flight'])
        self.assertEqual(self.p.get('a', 163)['body'], b'fixture')

    def test_simulated_100_revision_cycles(self):
        for i in range(100):
            t = 100 + 122*i
            revision = f'v{i}'
            body = revision.encode()
            p = AtomicPollCache(self.path)
            p.finish('a', p.reserve('a', t), t+1, 200, revision)
            p.finish_payload('a', p.reserve('a', t+61), t+62, 200, revision, body)
            self.assertEqual(p.get('a', t+63)['body'], body)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM payload').fetchone()[0], 1)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_safety(self):
        self.commit()
        r = self.p.get('a', 163)
        self.assertEqual((r['status'], r['live_trading'], r['production_recommendations']), ('HOLD','DISABLED','DISABLED'))
        self.assertFalse(r['model_input_allowed'])
        self.assertFalse(r['fresh_evidence'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
