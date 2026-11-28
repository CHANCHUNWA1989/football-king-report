import os
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from db_backup import backup, digest


class BackupTests(unittest.TestCase):
    def setUp(self):
        t = TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.src = self.root / 'source.db'
        self.dst = self.root / 'backup.db'
        with closing(sqlite3.connect(self.src)) as db, db:
            db.execute('CREATE TABLE example (value TEXT)')
            db.execute('INSERT INTO example VALUES (?)', ('fixture',))
        self.src.chmod(0o600)

    def test_backup_and_verified_rehearsal(self):
        initial = digest(self.src)
        r = backup(self.src, self.dst)
        self.assertEqual(r['source_sha256'], initial)
        self.assertEqual(r['backup_sha256'], digest(self.dst))
        self.assertEqual(r['status'], 'HOLD')
        self.assertFalse(r['automatic_restore'])
        self.assertEqual(digest(self.src), initial)
        rehearsal = self.root / 'rehearsal.db'
        backup(self.dst, rehearsal, expected_sha256=r['backup_sha256'])
        with closing(sqlite3.connect(rehearsal)) as db:
            self.assertEqual(db.execute('SELECT value FROM example').fetchall(), [('fixture',)])
        self.assertEqual(rehearsal.stat().st_mode & 0o777, 0o600)

    def test_no_overwrite(self):
        self.dst.write_bytes(b'untouched')
        with self.assertRaises(FileExistsError): backup(self.src, self.dst)
        self.assertEqual(self.dst.read_bytes(), b'untouched')

    def test_wrong_hash(self):
        with self.assertRaises(ValueError): backup(self.src, self.dst, expected_sha256='0'*64)
        self.assertFalse(self.dst.exists())

    def test_corruption(self):
        self.src.write_bytes(b'not sqlite')
        with self.assertRaises(sqlite3.DatabaseError): backup(self.src, self.dst)
        self.assertFalse(self.dst.exists())
        self.assertEqual(list(self.root.glob('.research-backup-*')), [])

    def test_sidecar_rejected(self):
        Path(str(self.src)+'-wal').touch()
        with self.assertRaises(ValueError): backup(self.src, self.dst)

    def test_symlink_and_hardlink_rejected(self):
        link = self.root / 'link.db'
        link.symlink_to(self.src)
        with self.assertRaises(ValueError): backup(link, self.dst)
        link.unlink()
        os.link(self.src, link)
        with self.assertRaises(ValueError): backup(self.src, self.dst)

    def test_public_permissions_rejected(self):
        self.src.chmod(0o644)
        with self.assertRaises(ValueError): backup(self.src, self.dst)
        self.src.chmod(0o600)
        self.root.chmod(0o755)
        with self.assertRaises(ValueError): backup(self.src, self.dst)
        self.root.chmod(0o700)

    def test_source_changed_rejected(self):
        import db_backup
        real = db_backup.digest
        def changing(path):
            result = real(path)
            if path != self.src:
                self.src.touch()
            return result
        with patch('db_backup.digest', side_effect=changing):
            with self.assertRaises(ValueError): backup(self.src, self.dst)
        self.assertFalse(self.dst.exists())

if __name__ == '__main__': unittest.main(verbosity=2)
