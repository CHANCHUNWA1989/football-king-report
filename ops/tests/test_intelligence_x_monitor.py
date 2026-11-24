import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from intelligence_x_monitor import HaltedMonitor, orphan_candidates


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root / 'halted.db'
        with sqlite3.connect(self.db) as c:
            c.execute('CREATE TABLE emergency_stop (id INTEGER PRIMARY KEY)')
            c.execute('INSERT INTO emergency_stop VALUES (1)')
            c.execute('CREATE TABLE jobs (state TEXT, token TEXT)')
        c.close()
        self.original = self.db.read_bytes()

    def monitor(self):
        return HaltedMonitor(self.db, expected_sha256=hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_valid(self):
        m = self.monitor()
        for _ in range(50):
            self.assertFalse(m.sample()['quarantined'])
        self.assertEqual(self.db.read_bytes(), self.original)

    def test_replacement_same_bytes(self):
        m = self.monitor()
        self.assertFalse(m.sample()['quarantined'])
        p = self.root / 'replacement'
        p.write_bytes(self.original)
        p.replace(self.db)
        self.assertEqual(m.sample()['reason'], 'FILE_REPLACED')

    def test_changed_bytes_sticky(self):
        m = self.monitor()
        self.assertFalse(m.sample()['quarantined'])
        self.db.write_bytes(self.original + b'x')
        self.assertEqual(m.sample()['reason'], 'DIGEST_MISMATCH')
        self.db.write_bytes(self.original)
        self.assertTrue(m.sample()['quarantined'])

    def test_missing_halt_even_with_matching_digest(self):
        with sqlite3.connect(self.db) as c:
            c.execute('DELETE FROM emergency_stop')
        c.close()
        self.assertEqual(self.monitor().sample()['reason'], 'HALT_MISSING')

    def test_active_lease_even_with_matching_digest(self):
        with sqlite3.connect(self.db) as c:
            c.execute("INSERT INTO jobs VALUES ('LEASED', 'synthetic')")
        c.close()
        self.assertEqual(self.monitor().sample()['reason'], 'ACTIVE_LEASE')

    def test_sidecar(self):
        m = self.monitor()
        Path(str(self.db) + '-wal').touch()
        self.assertEqual(m.sample()['reason'], 'SIDECAR_PRESENT')

    def test_symlink_and_missing(self):
        m = self.monitor()
        self.db.unlink()
        self.assertTrue(m.sample()['quarantined'])
        p = self.root / 'other'
        p.write_bytes(self.original)
        self.db.symlink_to(p)
        self.assertTrue(HaltedMonitor(self.db, expected_sha256=hashlib.sha256(self.original).hexdigest()).sample()['quarantined'])

    def test_orphan_inventory_only(self):
        fd, name = tempfile.mkstemp(prefix='.halted-recovery-', dir=self.root)
        os.close(fd)
        p = Path(name)
        (self.root / '.halted-recovery-abcdefgh').symlink_to(self.db)
        self.assertEqual(orphan_candidates(self.root), [p.name])
        self.assertTrue(p.exists())
        os.link(p, self.root / 'published')
        self.assertEqual(orphan_candidates(self.root), [])

    def test_nonprivate_directory(self):
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):
            orphan_candidates(self.root)

    def test_bad_pin(self):
        with self.assertRaises(ValueError):
            HaltedMonitor(self.db, expected_sha256='bad')
