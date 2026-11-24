import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence_x_audit import AuditedGate


class Stub:
    def __init__(self):
        self.calls = 0
        self.halts = 0

    def claim(self, job, *, now):
        self.calls += 1
        return {'token': 'synthetic-secret'}

    def finish(self, job, *, token, now):
        return False

    def halt(self):
        self.halts += 1


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'audit'
        self.path.touch(mode=0o600)
        s = self.path.stat()
        self.pin = (s.st_dev, s.st_ino)
        self.stub = Stub()

    def gate(self):
        return AuditedGate(self.stub, self.path, identity=self.pin, key=b'K'*32)

    def test_intent_outcome_no_identifiers(self):
        g = self.gate()
        self.assertTrue(g.claim('private-job', now=1))
        self.assertFalse(g.finish('private-job', token='synthetic-secret', now=2))
        raw = self.path.read_bytes()
        self.assertNotIn(b'private-job', raw)
        self.assertNotIn(b'synthetic-secret', raw)
        self.assertEqual([json.loads(l)[3] for l in raw.splitlines()], ['INTENT','GRANTED','INTENT','DENIED'])

    def test_tamper_blocks_new_call(self):
        self.gate().claim('x', now=1)
        self.path.write_bytes(self.path.read_bytes().replace(b'GRANTED', b'DENIED'))
        with self.assertRaisesRegex(ValueError, 'AUDIT_MAC'):
            self.gate().claim('x', now=2)
        self.assertEqual(self.stub.calls, 1)

    def test_missing_file_blocks(self):
        self.path.unlink()
        with self.assertRaises(OSError):
            self.gate().claim('x', now=1)
        self.assertEqual(self.stub.calls, 0)

    def test_replaced_file_blocks(self):
        p = self.path.with_name('replacement')
        p.touch(mode=0o600)
        p.replace(self.path)
        with self.assertRaisesRegex(ValueError, 'UNTRUSTED_AUDIT_FILE'):
            self.gate().claim('x', now=1)
        self.assertEqual(self.stub.calls, 0)

    def test_intent_fsync_failure_no_call(self):
        with patch('intelligence_x_audit.os.fsync', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):
                self.gate().claim('x', now=1)
        self.assertEqual(self.stub.calls, 0)
        with self.assertRaisesRegex(ValueError, 'UNFINISHED_INTENT'):
            self.gate().claim('x', now=2)

    def test_incomplete_after_operation_failure(self):
        with patch.object(self.stub, 'claim', side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):
                self.gate().claim('x', now=1)
        with self.assertRaisesRegex(ValueError, 'UNFINISHED_INTENT'):
            self.gate().claim('x', now=2)

    def test_halt_attempt_even_if_audit_missing(self):
        self.path.unlink()
        with self.assertRaises(OSError):
            self.gate().halt()
        self.assertEqual(self.stub.halts, 1)

    def test_partial_record_blocks(self):
        self.path.write_bytes(b'[')
        with self.assertRaisesRegex(ValueError, 'AUDIT_SIZE_OR_PARTIAL'):
            self.gate().claim('x', now=1)
        self.assertEqual(self.stub.calls, 0)

    def test_100_processes_in_batches(self):
        code = '''import sys,time
from intelligence_x_audit import AuditedGate
class Stub:
    def claim(self,job,*,now): return None
g=AuditedGate(Stub(),sys.argv[1],identity=tuple(map(int,sys.argv[2:])),key=b'K'*32)
for i in range(1000):
    try: g.claim('x',now=1); break
    except BlockingIOError: time.sleep(.005)
else: raise RuntimeError('lock timeout')
'''
        args = [sys.executable, '-S', '-c', code, str(self.path), *map(str,self.pin)]
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        ps = []
        try:
            for _ in range(10):
                ps = [subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(10)]
                for p in ps:
                    _, err = p.communicate(timeout=20)
                    self.assertEqual(p.returncode, 0, err)
        finally:
            for p in ps:
                if p.poll() is None:
                    p.kill(); p.communicate()
        with self.gate()._open() as f:
            self.assertEqual(self.gate()._read(f)[0], 200)
