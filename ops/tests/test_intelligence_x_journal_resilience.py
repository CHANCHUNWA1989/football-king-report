import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import intelligence_x_job_journal as journal


class JournalResilienceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'journal.sqlite'
        self.job = 'a' * 64

    def child(self, code):
        env = dict(os.environ, PYTHONPATH=str(Path(journal.__file__).parent))
        with subprocess.Popen([sys.executable, '-c', code, str(self.path), self.job],
                              env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True) as p:
            try:
                # Child explicitly signals when it reached the intended crash point.
                # communicate after kill is bounded; child alarm bounds readiness wait.
                self.assertEqual(p.stdout.readline().strip(), 'READY')
            finally:
                p.kill()
                p.communicate(timeout=5)
            self.assertNotEqual(p.returncode, 0)

    def test_committed_claim_survives_process_kill(self):
        self.child("import signal,sys,time; import intelligence_x_job_journal as j; "
                   "signal.alarm(10); j.claim(sys.argv[1],sys.argv[2],now=100); "
                   "print('READY',flush=True); time.sleep(30)")
        self.assertIsNone(journal.claim(self.path, self.job, now=159))
        b = journal.claim(self.path, self.job, now=160)
        self.assertEqual(b['attempt'], 2)
        self.assertTrue(journal.finish(self.path, self.job, token=b['token'], now=161))

    def test_uncommitted_transaction_rolls_back_on_kill(self):
        a = journal.claim(self.path, self.job, now=100)
        self.child("import signal,sys,time,sqlite3; signal.alarm(10); "
                   "c=sqlite3.connect(sys.argv[1],isolation_level=None); "
                   "c.execute('BEGIN IMMEDIATE'); c.execute(\"UPDATE jobs SET state='DONE'\"); "
                   "print('READY',flush=True); time.sleep(30)")
        self.assertTrue(journal.finish(self.path, self.job, token=a['token'], now=101))
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_locked_database_fails_closed_then_recovers(self):
        a = journal.claim(self.path, self.job, now=100)
        with sqlite3.connect(self.path, isolation_level=None) as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    journal.claim(self.path, 'b' * 64, now=100)
            finally:
                c.rollback()
        self.assertTrue(journal.finish(self.path, self.job, token=a['token'], now=101))
        self.assertIsNotNone(journal.claim(self.path, 'b' * 64, now=101))

    def test_capacity_retains_terminal_records_and_existing_leases(self):
        a = journal.claim(self.path, self.job, now=100)
        with sqlite3.connect(self.path) as c:
            c.executemany("INSERT INTO jobs VALUES (?, 'DONE', 1, NULL, 0, 100)",
                          [(hashlib.sha256(str(i).encode()).hexdigest(),)
                           for i in range(journal.MAX_JOBS-1)])
        with self.assertRaisesRegex(ValueError, 'JOURNAL_CAPACITY_EXCEEDED'):
            journal.claim(self.path, 'b' * 64, now=101)
        with self.assertRaisesRegex(ValueError, 'JOURNAL_CAPACITY_EXCEEDED'):
            journal.stop(self.path, 'c' * 64, now=101)
        self.assertTrue(journal.finish(self.path, self.job, token=a['token'], now=101))
        self.assertIsNone(journal.claim(self.path, self.job, now=102))
        with sqlite3.connect(self.path) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], journal.MAX_JOBS)
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')


if __name__ == '__main__':
    unittest.main()
