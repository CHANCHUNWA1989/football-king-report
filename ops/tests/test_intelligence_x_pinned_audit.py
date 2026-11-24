import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import intelligence_x_job_journal as journal
from intelligence_x_gate import JournalGate
from intelligence_x_pinned_audit import PinnedAuditedGate, claim_batch

JOB = 'a'*64


def identity(p):
    s = p.stat()
    return s.st_dev, s.st_ino


class Anchor:
    """Synthetic in-memory witness; not durable or external."""
    head = (0, '0'*64)

    def read(self):
        return self.head

    def advance(self, old, new):
        if self.head != old:
            return False
        self.head = new
        return True


class PinnedAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db = root / 'journal.db'
        self.state = root / 'gate'
        self.state.mkdir(mode=0o700)
        journal.stop(self.db, 'b'*64, now=1)
        self.gate = JournalGate(self.db, self.state, journal_identity=identity(self.db), state_identity=identity(self.state))
        self.audit = root / 'audit'
        self.audit.touch(mode=0o600)
        self.pin = identity(self.audit)
        self.anchor = Anchor()

    def wrapper(self):
        return PinnedAuditedGate(self.gate, self.audit, identity=self.pin, key=b'K'*32,
                                read_head=self.anchor.read, advance_head=self.anchor.advance)

    def test_real_claim_and_finish(self):
        lease = self.wrapper().claim(JOB, now=2)
        self.assertTrue(self.wrapper().finish(JOB, token=lease['token'], now=3))
        self.assertEqual(self.anchor.head[0], 4)
        self.assertEqual(journal.resource_snapshot(self.db)['done'], 1)
        self.assertNotIn(lease['token'].encode(), self.audit.read_bytes())

    def test_valid_prefix_rollback_blocks(self):
        self.wrapper().claim(JOB, now=2)
        old = self.audit.read_bytes()
        self.wrapper().claim(JOB, now=3)
        self.audit.write_bytes(old)
        with self.assertRaisesRegex(ValueError, 'AUDIT_HEAD_MISMATCH'):
            self.wrapper().claim('c'*64, now=4)
        self.assertTrue(journal.resource_snapshot(self.db)['halted'])

    def test_empty_rollback_blocks(self):
        self.wrapper().claim(JOB, now=2)
        self.audit.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'AUDIT_HEAD_MISMATCH'):
            self.wrapper().claim(JOB, now=3)
        self.assertTrue(journal.resource_snapshot(self.db)['halted'])

    def test_witness_unavailable(self):
        with patch.object(self.anchor, 'read', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                self.wrapper().claim(JOB, now=2)
        self.assertEqual(journal.resource_snapshot(self.db)['leased'], 0)
        self.assertTrue(journal.resource_snapshot(self.db)['halted'])

    def test_cas_rejected_after_commit(self):
        with patch.object(self.anchor, 'advance', return_value=False):
            with self.assertRaisesRegex(ValueError, 'WITNESS_ADVANCE_FAILED'):
                self.wrapper().claim(JOB, now=2)
        self.assertTrue(journal.resource_snapshot(self.db)['halted'])
        self.assertEqual(journal.resource_snapshot(self.db)['leased'], 0)

    def test_malformed_anchor(self):
        self.anchor.head = (True, '0'*64)
        with self.assertRaisesRegex(ValueError, 'INVALID_AUDIT_HEAD'):
            self.wrapper().claim(JOB, now=2)
        self.assertTrue(journal.resource_snapshot(self.db)['halted'])

    def test_batch_10_20_50_100(self):
        g = self.wrapper()
        for n in (10, 20, 50, 100):
            job = f'{n:064x}'
            self.assertEqual(claim_batch(g, [job]*n, now=2), dict(total=n, granted=1, denied=n-1, status='HOLD', production_recommendations='DISABLED'))
        self.assertEqual(self.anchor.head[0], 360)
        self.assertEqual(journal.resource_snapshot(self.db)['leased'], 4)

    def test_batch_rejects_invalid_input_without_mutation(self):
        for jobs, workers in [([JOB]*101,4),([JOB],5),(['bad'],4),([],4)]:
            with self.assertRaisesRegex(ValueError, 'INVALID_BATCH'):
                claim_batch(self.wrapper(), jobs, now=2, workers=workers)
        self.assertEqual(self.anchor.head[0], 0)
        self.assertEqual(journal.resource_snapshot(self.db)['leased'], 0)
