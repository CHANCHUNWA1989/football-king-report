"""Offline snapshot comparison, not a trusted anti-rollback service."""
import re
import time
from contextlib import closing
from db_backup import private_path, source_stat, digest, inspect, MAX_SECONDS
from persistent_poll_policy import PersistentPollPolicy, MAX_STATE_BYTES, valid_time


def review(path, expected_sha256, expected_serial, expected_clock):
    """Compare against caller-supplied checkpoint; never authorize resume."""
    if (not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256)
            or type(expected_serial) is not int or expected_serial < 0 or not valid_time(expected_clock)):
        raise ValueError('invalid checkpoint')
    path = private_path(path)
    before = source_stat(path)
    if digest(path) != expected_sha256:
        raise ValueError('snapshot hash mismatch')
    with closing(inspect(path, time.monotonic() + MAX_SECONDS)) as db:
        row = db.execute('SELECT state FROM policy WHERE id=1 AND length(CAST(state AS BLOB))<=?', (MAX_STATE_BYTES,)).fetchone()
        if row is None:
            raise ValueError('missing policy state')
        policy = PersistentPollPolicy._decode(row[0])
        if policy._serial != expected_serial or policy._clock != expected_clock:
            raise ValueError('snapshot checkpoint mismatch')
    if source_stat(path) != before or digest(path) != expected_sha256:
        raise ValueError('snapshot changed during review')
    return {'schema':'recovery-review-v1','checkpoint_match':True,'external_anchor_authenticated':False,
            'rollback_protection':False,'resume_allowed':False,'automatic_restore':False,
            'active_leases':sum(s.lease is not None for s in policy._scopes.values()),
            'halted_scopes':sum(s.halted for s in policy._scopes.values()),
            'status':'HOLD','model_input_allowed':False,'live_trading':'DISABLED','production_recommendations':'DISABLED'}


if __name__ == '__main__':
    import unittest
    from pathlib import Path
    from tempfile import TemporaryDirectory
    from atomic_poll_cache import AtomicPollCache
    from db_backup import backup

    class Tests(unittest.TestCase):
        def setUp(self):
            tmp = TemporaryDirectory()
            self.addCleanup(tmp.cleanup)
            self.root = Path(tmp.name)
            self.src = self.root / 'state.db'
            self.store = AtomicPollCache.initialize(self.src, ['a'])

        def test_matching_checkpoint_never_allows_resume(self):
            before = digest(self.src)
            result = review(self.src, before, 0, 0)
            self.assertTrue(result['checkpoint_match'])
            for k in ('external_anchor_authenticated','rollback_protection','resume_allowed','automatic_restore','model_input_allowed'):
                self.assertIs(result[k], False)
            self.assertEqual(result['status'], 'HOLD')
            self.assertEqual(digest(self.src), before)

        def test_newer_checkpoint_rejects_old_snapshot(self):
            old = self.root / 'old.db'
            backup(self.src, old)
            self.store.reserve('a', 100)
            with self.assertRaises(ValueError): review(old, digest(self.src), 1, 100)
            with self.assertRaises(ValueError): review(old, digest(old), 1, 100)

        def test_active_lease_remains_blocked(self):
            self.store.reserve('a', 100)
            self.assertEqual(review(self.src, digest(self.src), 1, 100)['active_leases'], 1)
            self.assertIsNone(self.store.reserve('a', 100000))

        def test_halted_scope_remains_blocked(self):
            self.store.finish('a', self.store.reserve('a', 100), 101, 403)
            self.assertEqual(review(self.src, digest(self.src), 1, 101)['halted_scopes'], 1)

        def test_invalid_checkpoint(self):
            for args in [('0'*64, 0, 0), (digest(self.src), True, 0), (digest(self.src), 0, float('nan'))]:
                with self.subTest(args=args), self.assertRaises(ValueError): review(self.src, *args)

    unittest.main(verbosity=2)
