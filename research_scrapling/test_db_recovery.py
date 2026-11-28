"""Synthetic disaster-recovery rehearsal; never authorize a restored live store."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from atomic_poll_cache import AtomicPollCache
from db_backup import backup, digest


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        self.path = self.root / 'source.db'
        self.store = AtomicPollCache.initialize(self.path, ['a'])

    def copy(self, label):
        archived = self.root / (label + '-backup.db')
        restored = self.root / (label + '-rehearsal.db')
        report = backup(self.path, archived)
        self.assertFalse(report['automatic_restore'])
        self.assertFalse(report['rollback_protection'])
        self.assertEqual(report['status'], 'HOLD')
        backup(archived, restored, expected_sha256=report['backup_sha256'])
        self.assertEqual(digest(archived), report['backup_sha256'])
        return AtomicPollCache(restored)

    def test_abandoned_revision_lease(self):
        self.assertIsNotNone(self.store.reserve('a', 100))
        clone = self.copy('revision')
        self.assertTrue(clone.snapshot('a')['in_flight'])
        self.assertIsNone(clone.reserve('a', 100000))
        self.assertIsNone(clone.get('a', 100001)['body'])

    def test_abandoned_payload_lease(self):
        self.store.finish('a', self.store.reserve('a', 100), 101, 200, 'v1')
        self.assertIsNotNone(self.store.reserve('a', 161))
        clone = self.copy('payload')
        self.assertTrue(clone.snapshot('a')['in_flight'])
        self.assertIsNone(clone.reserve('a', 100000))
        self.assertIsNone(clone.get('a', 100001)['body'])

    def test_provider_halt_survives_copy(self):
        self.store.finish('a', self.store.reserve('a', 100), 101, 403)
        clone = self.copy('halt')
        self.assertIsNone(clone.reserve('a', 100000))
        self.assertIsNone(clone.get('a', 100001)['body'])

    def test_backoff_survives_copy(self):
        self.store.finish('a', self.store.reserve('a', 100), 101, 429, retry_after=7200)
        clone = self.copy('backoff')
        self.assertIsNone(clone.reserve('a', 7300))
        self.assertIsNotNone(clone.reserve('a', 7301))

    def test_100_revision_backup_recovery_cycles(self):
        for i in range(100):
            t = 100 + 122*i
            rev = f'v{i}'
            payload = rev.encode()
            self.store.finish('a', self.store.reserve('a', t), t+1, 200, rev)
            self.store.finish_payload('a', self.store.reserve('a', t+61), t+62, 200, rev, payload)
            before = digest(self.path)
            clone = self.copy(str(i))
            self.assertEqual(digest(self.path), before)
            r = clone.get('a', t+63)
            self.assertEqual(r['body'], payload)
            self.assertEqual(r['status'], 'HOLD')
            self.assertFalse(r['model_input_allowed'])
            self.assertFalse(r['fresh_evidence'])
            self.assertEqual(r['live_trading'], 'DISABLED')
            self.assertEqual(r['production_recommendations'], 'DISABLED')
            self.assertIsNone(clone.get('a', t+363)['body'])

    def test_old_snapshot_does_not_prove_rollback_safety(self):
        clone = self.copy('old')
        self.store.reserve('a', 100)
        self.assertTrue(self.store.snapshot('a')['in_flight'])
        # A backup taken before reservation does not know of that later lease.
        # Never substitute this clone for active state; external monotonic evidence needed.
        self.assertIsNotNone(clone.reserve('a', 100))


if __name__ == '__main__':
    unittest.main(verbosity=2)
