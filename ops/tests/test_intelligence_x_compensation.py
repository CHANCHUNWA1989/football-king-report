import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import intelligence_x_job_journal as journal
from intelligence_x_gate import JournalGate
from intelligence_x_pinned_audit import CompensationFailed, PinnedAuditedGate, claim_batch


class CompensationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.db, self.state, self.audit = root/'db', root/'gate', root/'audit'
        self.state.mkdir(mode=0o700)
        self.audit.touch(mode=0o600)
        journal.stop(self.db, '0'*64, now=1)
        def identity(p):
            s = p.stat()
            return s.st_dev, s.st_ino
        self.raw = JournalGate(self.db, self.state, journal_identity=identity(self.db), state_identity=identity(self.state))
        self.pin = identity(self.audit)
        self.head = (0, '0'*64)
        self.gate = self.wrapper()

    def advance(self, old, new):
        if old != self.head:
            return False
        self.head = new
        return True

    def wrapper(self):
        return PinnedAuditedGate(self.raw, self.audit, identity=self.pin, key=b'X'*32,
                                 read_head=lambda: self.head, advance_head=self.advance)

    def assert_halted(self):
        snap = journal.resource_snapshot(self.db)
        self.assertTrue(snap['halted'])
        self.assertEqual(snap['leased'], 0)
        self.assertTrue((self.state/'QUARANTINED').is_file())
        self.assertIsNone(self.raw.claim('f'*64, now=4))

    def test_batch_second_cas_failure_revokes_prior_and_stops_dispatch(self):
        original = self.gate.advance_head
        calls = []
        def advance(old, new):
            calls.append(new)
            return original(old, new) if len(calls) == 1 else False
        self.gate.advance_head = advance
        with self.assertRaisesRegex(ValueError, 'WITNESS_ADVANCE_FAILED'):
            claim_batch(self.gate, ['a'*64, 'b'*64, 'c'*64], now=2)
        self.assertEqual(len(calls), 2)
        self.assert_halted()

    def test_audit_missing_revokes_prior_lease(self):
        self.gate.claim('a'*64, now=2)
        self.audit.unlink()
        with self.assertRaises(FileNotFoundError):
            self.gate.claim('b'*64, now=3)
        self.assert_halted()

    def test_outcome_write_failure_after_mutation(self):
        append = self.gate._append
        def fail(f, seq, previous, action, phase):
            if phase != 'INTENT':
                self.assertEqual(journal.resource_snapshot(self.db)['leased'], 1)
                raise OSError('outcome write failed')
            return append(f, seq, previous, action, phase)
        with patch.object(self.gate, '_append', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'outcome write failed'):
                self.gate.claim('a'*64, now=2)
        self.assert_halted()

    def test_interrupt_after_mutation(self):
        with patch.object(self.gate, 'advance_head', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.gate.claim('a'*64, now=2)
        self.assert_halted()

    def test_compensation_failure_preserves_both_errors_and_blocks_instance(self):
        primary = ValueError('synthetic witness failure')
        secondary = OSError('synthetic halt failure')
        with patch.object(self.gate, 'advance_head', side_effect=primary), patch.object(self.raw, 'halt', side_effect=secondary):
            with self.assertRaises(CompensationFailed) as ctx:
                self.gate.claim('a'*64, now=2)
        self.assertIs(ctx.exception.original, primary)
        self.assertIs(ctx.exception.halt_error, secondary)
        self.assertIs(ctx.exception.__cause__, primary)
        with self.assertRaisesRegex(RuntimeError, 'GATE_FAILED'):
            self.gate.claim('b'*64, now=3)
        self.gate.recover_halted()
        self.assert_halted()

    def test_explicit_restart_halts_even_when_witness_matches(self):
        self.gate.claim('a'*64, now=2)
        fresh = self.wrapper()
        fresh.recover_halted()
        self.assert_halted()
        with self.assertRaisesRegex(RuntimeError, 'GATE_FAILED'):
            fresh.claim('b'*64, now=3)

    def test_healthy_halt_audited(self):
        self.gate.claim('a'*64, now=2)
        self.gate.halt()
        self.assertEqual(self.head[0], 4)
        self.assert_halted()


if __name__ == '__main__':
    unittest.main()
