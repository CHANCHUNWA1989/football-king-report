import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from intelligence_x_recovery import recover_halted


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = Path(self.tmp.name) / 'old.db'
        self.dst = Path(self.tmp.name) / 'recovered.db'
        self.change('CREATE TABLE IF NOT EXISTS jobs (job TEXT PRIMARY KEY, state TEXT NOT NULL, attempt INTEGER NOT NULL, token TEXT, deadline INTEGER NOT NULL, last_seen INTEGER NOT NULL)')
        self.change('CREATE TABLE IF NOT EXISTS emergency_stop (id INTEGER PRIMARY KEY CHECK(id=1))')
        self.change("INSERT INTO jobs VALUES (?, 'LEASED', 1, ?, 160, 100)", ('a'*64, 'b'*32))

    def change(self, sql, params=()):
        conn = sqlite3.connect(self.src)
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def recover(self):
        return recover_halted(self.src, self.dst, expected_sha256=hashlib.sha256(self.src.read_bytes()).hexdigest())

    def test_old_running_backup_always_halted(self):
        original = self.src.read_bytes()
        self.assertTrue(self.recover()['halted'])
        self.assertEqual(self.src.read_bytes(), original)
        conn = sqlite3.connect(self.dst)
        try:
            self.assertEqual(conn.execute('SELECT id FROM emergency_stop').fetchall(), [(1,)])
            self.assertEqual(conn.execute('SELECT state,token FROM jobs').fetchall(), [('STOPPED', None)])
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone(), ('ok',))
        finally:
            conn.close()

    def test_existing_halt_retained(self):
        self.change('INSERT INTO emergency_stop VALUES (1)')
        self.assertTrue(self.recover()['halted'])

    def test_digest_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'DIGEST_MISMATCH'):
            recover_halted(self.src, self.dst, expected_sha256='0'*64)
        self.assertFalse(self.dst.exists())

    def test_no_overwrite(self):
        self.dst.write_bytes(b'keep')
        with self.assertRaises(ValueError):
            self.recover()
        self.assertEqual(self.dst.read_bytes(), b'keep')

    def test_unknown_schema(self):
        self.change('CREATE TABLE extra (x INT)')
        with self.assertRaisesRegex(ValueError, 'UNSUPPORTED_SCHEMA'):
            self.recover()
        self.assertFalse(self.dst.exists())

    def test_invalid_state(self):
        self.change("UPDATE jobs SET state='RUNNING'")
        with self.assertRaisesRegex(ValueError, 'INVALID_JOB_STATE'):
            self.recover()
        self.assertFalse(self.dst.exists())

    def test_sidecar(self):
        Path(str(self.src)+'-wal').touch()
        with self.assertRaises(ValueError):
            self.recover()
        self.assertFalse(self.dst.exists())

    def test_corrupt_snapshot(self):
        self.src.write_bytes(b'not a database')
        with self.assertRaises(ValueError):
            self.recover()
        self.assertFalse(self.dst.exists())
