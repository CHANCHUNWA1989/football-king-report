import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from atomic_poll_cache import AtomicPollCache
from research_adapter import FixtureResponse as R, FixtureTransport, step


class AdapterTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / 'state.db'
        self.store = AtomicPollCache.initialize(self.path, ['a'])

    def tick(self, transport, t):
        return step(self.store, 'a', t, transport)

    def test_success_two_steps(self):
        tr = FixtureTransport([R(200,'v1'), R(200,'v1',b'fixture')])
        self.assertEqual(self.tick(tr,100)['outcome'],'RESEARCH_PAYLOAD_PENDING')
        self.assertEqual(self.tick(tr,159)['action'],'BLOCKED')
        self.assertEqual(self.tick(tr,160)['outcome'],'RESEARCH_CACHE_REVISION_COMMITTED')
        self.assertEqual(tr.calls,['revision','payload'])
        self.assertEqual(self.store.get('a',161)['body'],b'fixture')

    def test_429(self):
        tr = FixtureTransport([R(429,retry_after=7200)])
        self.assertEqual(self.tick(tr,100)['outcome'],'HOLD_ERROR')
        self.assertEqual(self.tick(tr,7299)['action'],'BLOCKED')
        self.assertEqual(len(tr.calls),1)

    def test_403_halt(self):
        tr = FixtureTransport([R(403)])
        self.tick(tr,100)
        self.store = AtomicPollCache(self.path)
        self.assertEqual(self.tick(tr,99999)['action'],'BLOCKED')
        self.assertEqual(len(tr.calls),1)

    def test_invalid_response(self):
        tr = FixtureTransport([{'status':200}])
        self.assertEqual(self.tick(tr,100)['outcome'],'HOLD_ERROR')
        self.assertFalse(self.store.snapshot('a')['in_flight'])

    def test_invalid_payload(self):
        tr = FixtureTransport([R(200,'v1'),R(200,'v1',b'')])
        self.tick(tr,100)
        self.assertEqual(self.tick(tr,160)['outcome'],'HOLD_ERROR')
        self.assertIsNone(self.store.get('a',161)['body'])

    def test_database_failure_preserves_lease(self):
        tr = FixtureTransport([R(200,'v1'),R(200,'v1',b'x')])
        self.tick(tr,100)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TRIGGER fail_write BEFORE INSERT ON payload BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(sqlite3.Error):self.tick(tr,160)
        self.assertEqual(self.tick(tr,9999)['action'],'BLOCKED')
        self.assertEqual(len(tr.calls),2)

    def test_external_transport_rejected(self):
        with self.assertRaises(ValueError):self.tick(object(),100)
        self.assertFalse(self.store.snapshot('a')['in_flight'])

    def test_safety_flags(self):
        r=self.tick(FixtureTransport([R(200,'v1')]),100)
        self.assertEqual((r['status'],r['live_trading'],r['production_recommendations']),('HOLD','DISABLED','DISABLED'))
        for k in ('model_input_allowed','fresh_evidence','network_enabled'):self.assertFalse(r[k])

if __name__=='__main__':unittest.main(verbosity=2)
