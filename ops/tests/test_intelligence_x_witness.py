import errno
import hashlib
import hmac
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence_x_witness import recover_witnessed
from intelligence_x_recovery import recover_halted


class WitnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / 'old.db'
        self.dst = Path(self.tmp.name) / 'new.db'
        with sqlite3.connect(self.src) as conn:
            conn.execute('CREATE TABLE jobs (job TEXT PRIMARY KEY, state TEXT NOT NULL, attempt INTEGER NOT NULL, token TEXT, deadline INTEGER NOT NULL, last_seen INTEGER NOT NULL)')
            conn.execute('CREATE TABLE emergency_stop (id INTEGER PRIMARY KEY CHECK(id=1))')
            conn.execute("INSERT INTO jobs VALUES (?, 'LEASED', 1, ?, 160, 100)", ('a'*64, 'b'*32))
        conn.close()
        self.digest = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.key = b'X'*32  # synthetic only
        self.jid = 'c'*64

    def checkpoint(self, gen=2, jid=None, digest=None):
        jid, digest = jid or self.jid, digest or self.digest
        msg = f'intelligence-x-backup-v1\n{jid}\n{gen}\n{digest}\n'.encode('ascii')
        return dict(journal_id=jid, generation=gen, digest=digest, mac=hmac.digest(self.key, msg, 'sha256').hex())

    def recover(self, cp=None, **overrides):
        args = dict(checkpoint=self.checkpoint() if cp is None else cp, key=self.key,
                    expected_journal_id=self.jid, expected_generation=2, expected_digest=self.digest)
        args.update(overrides)
        return recover_witnessed(self.src, self.dst, **args)

    def test_current_checkpoint(self):
        self.assertTrue(self.recover()['halted'])
        with sqlite3.connect(self.dst) as conn:
            self.assertEqual(conn.execute('SELECT id FROM emergency_stop').fetchall(), [(1,)])
            self.assertEqual(conn.execute('SELECT state, token FROM jobs').fetchall(), [('STOPPED', None)])
        conn.close()

    def test_signed_old_future_and_other_journal_rejected(self):
        for cp in (self.checkpoint(1), self.checkpoint(3), self.checkpoint(jid='d'*64), self.checkpoint(digest='0'*64)):
            with self.assertRaisesRegex(ValueError, 'CHECKPOINT_NOT_CURRENT'):
                self.recover(cp)
            self.assertFalse(self.dst.exists())

    def test_mac_and_key(self):
        with self.assertRaisesRegex(ValueError, 'INVALID_WITNESS_MAC'):
            self.recover(dict(self.checkpoint(), mac='0'*64))
        with self.assertRaises(ValueError):
            self.recover(key=b'Y'*32)
        with self.assertRaises(ValueError):
            self.recover(key=b'')
        self.assertFalse(self.dst.exists())

    def test_bad_checkpoint_and_pin(self):
        for cp in ({}, dict(self.checkpoint(), extra=True), dict(self.checkpoint(), generation=True)):
            with self.assertRaises(ValueError):
                self.recover(cp)
        with self.assertRaises(ValueError):
            self.recover(expected_generation=None)
        self.assertFalse(self.dst.exists())

    def test_replaced_source_bytes(self):
        self.src.write_bytes(self.src.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'DIGEST_MISMATCH'):
            self.recover()
        self.assertFalse(self.dst.exists())

    def test_simulated_enospc(self):
        for target in ('os.fsync', 'os.link'):
            with patch('intelligence_x_recovery.'+target, side_effect=OSError(errno.ENOSPC, 'synthetic disk full')):
                with self.assertRaises(OSError):
                    self.recover()
            self.assertFalse(self.dst.exists())
            self.assertEqual(list(self.dst.parent.glob('.halted-recovery-*')), [])

    def test_real_process_exit_before_and_after_publish(self):
        script = '''import os, sys
from intelligence_x_recovery import recover_halted
real = os.link
def interrupted(src, dst):
    if sys.argv[4] == 'after': real(src, dst)
    os._exit(77)
os.link = interrupted
recover_halted(sys.argv[1], sys.argv[2], expected_sha256=sys.argv[3])
'''
        for stage in ('before', 'after'):
            p = subprocess.run([sys.executable, '-c', script, str(self.src), str(self.dst), self.digest, stage],
                               env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])), timeout=10)
            self.assertEqual(p.returncode, 77)
            if stage == 'before':
                self.assertFalse(self.dst.exists())
            else:
                with sqlite3.connect(self.dst) as conn:
                    self.assertEqual(conn.execute('SELECT id FROM emergency_stop').fetchall(), [(1,)])
                    self.assertEqual(conn.execute('PRAGMA integrity_check').fetchall(), [('ok',)])
                conn.close()

    def test_10000_mutated_macs(self):
        cp = self.checkpoint()
        for n in range(10000):
            bad = dict(cp, mac=f'{n:064x}')
            self.assertNotEqual(bad['mac'], cp['mac'])
            with self.assertRaisesRegex(ValueError, 'INVALID_WITNESS_MAC'):
                self.recover(bad)
        self.assertFalse(self.dst.exists())
