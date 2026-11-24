import hashlib
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from collections import namedtuple
from contextlib import closing

import intelligence_x_job_journal as j


class GlobalStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'journal.sqlite'
        self.job = 'a' * 64

    def test_halt_before_any_job(self):
        j.halt_all(self.path)
        self.assertIsNone(j.claim(self.path, self.job, now=100))
        self.assertTrue(j.resource_snapshot(self.path)['halted'])

    def test_revokes_existing_lease(self):
        a = j.claim(self.path, self.job, now=100)
        j.halt_all(self.path)
        self.assertFalse(j.finish(self.path, self.job, token=a['token'], now=101))
        self.assertIsNone(j.claim(self.path, self.job, now=1000))
        self.assertEqual(j.resource_snapshot(self.path)['stopped'], 1)

    def test_idempotent_halt(self):
        j.halt_all(self.path)
        j.halt_all(self.path)
        self.assertEqual(j.resource_snapshot(self.path)['total'], 0)

    def test_concurrent_claim_and_halt(self):
        jobs = [hashlib.sha256(str(i).encode()).hexdigest() for i in range(32)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(j.claim, self.path, k, now=100) for k in jobs[:16]]
            stop = pool.submit(j.halt_all, self.path)
            futures += [pool.submit(j.claim, self.path, k, now=100) for k in jobs[16:]]
            stop.result()
            for k, f in zip(jobs, futures):
                a = f.result()
                if a:
                    self.assertFalse(j.finish(self.path, k, token=a['token'], now=101))
        self.assertEqual(j.resource_snapshot(self.path)['leased'], 0)
        self.assertIsNone(j.claim(self.path, self.job, now=102))

    def test_readonly_missing_path(self):
        with self.assertRaises(FileNotFoundError):
            j.resource_snapshot(self.path)
        self.assertFalse(self.path.exists())

    def test_snapshot_no_tokens_and_no_write(self):
        a = j.claim(self.path, self.job, now=100)
        before = self.path.read_bytes()
        r = j.resource_snapshot(self.path)
        self.assertEqual(r['leased'], 1)
        self.assertNotIn(a['token'], str(r))
        self.assertNotIn(self.job, str(r))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(r['status'], 'HOLD')

    def test_capacity_and_disk_warning(self):
        j.claim(self.path, self.job, now=100)
        with patch.object(j, 'MAX_JOBS', 1), patch.object(j.shutil, 'disk_usage', return_value=namedtuple('Usage', 'total used free')(100, 99, 1)):
            r = j.resource_snapshot(self.path)
        self.assertTrue(r['capacity_warning'])
        self.assertTrue(r['disk_warning'])

    def test_backup_readback_only(self):
        j.claim(self.path, self.job, now=100)
        j.halt_all(self.path)
        copy = Path(self.tmp.name) / 'backup.sqlite'
        with closing(sqlite3.connect(self.path)) as src, closing(sqlite3.connect(copy)) as dst:
            src.backup(dst)
            self.assertEqual(dst.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertTrue(j.resource_snapshot(copy)['halted'])
        self.assertEqual(j.resource_snapshot(copy)['stopped'], 1)
        self.assertIsNone(j.claim(copy, 'b' * 64, now=100))


if __name__ == '__main__':
    unittest.main()
