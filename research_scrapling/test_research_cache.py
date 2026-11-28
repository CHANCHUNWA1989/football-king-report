import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from research_cache import ResearchCache, MAX_BYTES


class CacheTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'cache.db'
        self.c = ResearchCache.initialize(self.path, ['a', 'b'])

    def put(self):
        return self.c.put('a', 'v1', b'fixture', 100)

    def test_miss(self):
        self.assertEqual(self.c.get('a','v1',100)['cache_state'],'MISS')

    def test_restart(self):
        self.put()
        self.assertEqual(ResearchCache(self.path).get('a','v1',101)['body'],b'fixture')

    def test_boundary(self):
        self.put()
        self.assertEqual(self.c.get('a','v1',400)['cache_state'],'HIT_RESEARCH_ONLY')
        self.assertIsNone(self.c.get('a','v1',401)['body'])

    def test_revision_mismatch(self):
        self.put()
        self.assertIsNone(self.c.get('a','v2',101)['body'])

    def test_same_revision_no_refresh(self):
        self.put()
        self.assertEqual(self.c.put('a','v1',b'fixture',399)['cache_state'],'UNCHANGED_NO_REFRESH')
        self.assertEqual(self.c.get('a','v1',401)['cache_state'],'EXPIRED')

    def test_same_revision_conflict(self):
        self.put()
        with self.assertRaises(ValueError):
            self.c.put('a','v1',b'changed',101)
        self.assertEqual(self.c.get('a','v1',101)['body'],b'fixture')

    def test_new_revision(self):
        self.put()
        self.c.put('a','v2',b'new',101)
        self.assertIsNone(self.c.get('a','v1',102)['body'])
        self.assertEqual(self.c.get('a','v2',102)['body'],b'new')

    def test_corrupt_body(self):
        self.put()
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE cache SET body=? WHERE scope=?',(b'corrupt','a'))
        with self.assertRaises(ValueError):
            self.c.get('a','v1',101)

    def test_corrupt_metadata(self):
        self.put()
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE cache SET captured=99 WHERE scope=?',('a',))
        with self.assertRaises(ValueError):
            self.c.get('a','v1',101)

    def test_clock_rollback(self):
        self.put()
        self.c.get('a','v1',102)
        with self.assertRaises(ValueError):
            ResearchCache(self.path).get('a','v1',101)

    def test_size(self):
        with self.assertRaises(ValueError):
            self.c.put('a','v1',b'x'*(MAX_BYTES+1),100)

    def test_no_recreate(self):
        self.path.unlink()
        with self.assertRaises(sqlite3.Error):
            self.c.get('a','v1',100)
        self.assertFalse(self.path.exists())

    def test_scope_isolation(self):
        self.put()
        self.assertIsNone(self.c.get('b','v1',101)['body'])

    def test_safety(self):
        self.put()
        r=self.c.get('a','v1',101)
        self.assertEqual((r['status'],r['live_trading'],r['production_recommendations']),('HOLD','DISABLED','DISABLED'))
        for key in ('model_input_allowed','network_enabled','fresh_evidence'):
            self.assertFalse(r[key])

if __name__=='__main__':
    unittest.main(verbosity=2)
