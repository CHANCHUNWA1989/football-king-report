import hashlib
import hmac
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import intelligence_x_job_journal as journal
from intelligence_x_gate import JournalGate
from intelligence_x_monitor import HaltedMonitor
from intelligence_x_witness import recover_witnessed

JOB = 'a'*64
OTHER = 'b'*64


def identity(p):
    s = p.stat()
    return (s.st_dev, s.st_ino)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'jobs.db'
        self.state = self.root / 'gate'
        self.state.mkdir(mode=0o700)
        journal.stop(self.db, OTHER, now=1)
        self.pins = dict(journal_identity=identity(self.db), state_identity=identity(self.state))

    def gate(self):
        return JournalGate(self.db, self.state, **self.pins)

    def test_normal_synthetic_lease(self):
        lease = self.gate().claim(JOB, now=2)
        self.assertTrue(self.gate().finish(JOB, token=lease['token'], now=3))

    def test_latch_survives_restart_and_old_backup(self):
        old = self.db.read_bytes()
        lease = self.gate().claim(JOB, now=2)
        self.gate().halt()
        self.db.write_bytes(old)
        self.assertIsNone(self.gate().claim(JOB, now=4))
        self.assertFalse(self.gate().finish(JOB, token=lease['token'], now=4))
        code = """import sys
from intelligence_x_gate import JournalGate
g=JournalGate(sys.argv[1],sys.argv[2],journal_identity=tuple(map(int,sys.argv[3:5])),state_identity=tuple(map(int,sys.argv[5:7])))
assert g.claim('a'*64,now=4) is None
"""
        subprocess.run([sys.executable, '-c', code, str(self.db), str(self.state),
                        *map(str, self.pins['journal_identity']), *map(str, self.pins['state_identity'])],
                       env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
                       check=True, timeout=10)

    def test_replacement_latches(self):
        p = self.root / 'new'
        p.write_bytes(self.db.read_bytes())
        p.replace(self.db)
        with self.assertRaisesRegex(ValueError, 'JOURNAL_REPLACED'):
            self.gate().claim(JOB, now=2)
        self.assertIsNone(self.gate().claim(JOB, now=2))

    def test_missing_directory_denies(self):
        self.state.rmdir()
        with self.assertRaises(OSError):
            self.gate().claim(JOB, now=2)
        self.assertEqual(journal.resource_snapshot(self.db)['leased'], 0)

    def test_latch_before_halt_failure(self):
        with patch('intelligence_x_gate.journal.halt_all', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):
                self.gate().halt()
        self.assertIsNone(self.gate().claim(JOB, now=2))

    def test_latch_write_failure_no_journal_mutation(self):
        with patch('intelligence_x_gate.os.fsync', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):
                self.gate().halt()
        self.assertFalse(journal.resource_snapshot(self.db)['halted'])
        self.assertIsNone(self.gate().claim(JOB, now=2))

    def test_multi_process_claim(self):
        code = '''import sys, time
from intelligence_x_gate import JournalGate
g=JournalGate(sys.argv[1],sys.argv[2],journal_identity=tuple(map(int,sys.argv[3:5])),state_identity=tuple(map(int,sys.argv[5:7])))
for i in range(200):
    try:
        print('GRANTED' if g.claim('a'*64,now=2) else 'DENIED'); break
    except BlockingIOError: time.sleep(.005)
else: raise RuntimeError('lock timeout')
'''
        args = [sys.executable, '-c', code, str(self.db), str(self.state), *map(str, self.pins['journal_identity']), *map(str, self.pins['state_identity'])]
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        ps = [subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env) for _ in range(12)]
        try:
            results = [p.communicate(timeout=15) for p in ps]
            self.assertTrue(all(p.returncode == 0 for p in ps), results)
            self.assertEqual(sum(out.strip() == 'GRANTED' for out, _ in results), 1)
        finally:
            for p in ps:
                if p.poll() is None:
                    p.kill()
                    p.communicate()

    def test_end_to_end_real_journal_recovery(self):
        lease = self.gate().claim(JOB, now=2)
        digest = hashlib.sha256(self.db.read_bytes()).hexdigest()
        jid, key = 'c'*64, b'X'*32
        mac = hmac.digest(key, f'intelligence-x-backup-v1\n{jid}\n1\n{digest}\n'.encode(), 'sha256').hex()
        dst = self.root / 'restored.db'
        recover_witnessed(self.db, dst, checkpoint=dict(journal_id=jid,generation=1,digest=digest,mac=mac), key=key, expected_journal_id=jid, expected_generation=1, expected_digest=digest)
        m = HaltedMonitor(dst, expected_sha256=hashlib.sha256(dst.read_bytes()).hexdigest())
        self.assertFalse(m.sample()['quarantined'])
        g = JournalGate(dst, self.state, journal_identity=identity(dst), state_identity=identity(self.state))
        self.assertIsNone(g.claim(JOB, now=4))
        self.assertFalse(g.finish(JOB, token=lease['token'], now=4))
        self.assertTrue((self.state / 'QUARANTINED').exists())
        self.assertFalse(journal.finish(dst, JOB, token=lease['token'], now=4))
