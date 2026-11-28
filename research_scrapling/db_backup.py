"""Offline, quiescent research database backup; never restores live state.
Caller must stop ALL writers and use a trusted, private local directory.
Integrity and SHA-256 detect corruption, not malicious replacement or rollback.
"""
import hashlib
import os
import re
import sqlite3
import stat
import tempfile
import time
from contextlib import closing
from pathlib import Path

MAX_BYTES = 128 * 1024 * 1024
MAX_SECONDS = 30


def private_path(path):
    path = Path(path).absolute()
    parent = path.parent
    s = parent.stat()
    if parent.resolve() != parent or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise ValueError('private local directory required')
    return path


def source_stat(path):
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077 or s.st_nlink != 1 or not 0 < s.st_size <= MAX_BYTES:
        raise ValueError('unsafe database file')
    for suffix in ('-wal', '-shm', '-journal'):
        if os.path.lexists(str(path) + suffix):
            raise ValueError('quiescent database without sidecars required')
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def digest(path):
    h = hashlib.sha256()
    count = 0
    with path.open('rb') as stream:
        while chunk := stream.read(65536):
            count += len(chunk)
            if count > MAX_BYTES:
                raise ValueError('database too large')
            h.update(chunk)
    return h.hexdigest()


def inspect(path, deadline):
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)
    try:
        db.execute('PRAGMA trusted_schema=OFF')
        if db.execute('PRAGMA trusted_schema').fetchone() != (0,):
            raise RuntimeError('trusted_schema unavailable')
        db.setconfig(sqlite3.SQLITE_DBCONFIG_DEFENSIVE, True)
        db.setconfig(sqlite3.SQLITE_DBCONFIG_ENABLE_LOAD_EXTENSION, False)
        db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000)
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        if db.execute('PRAGMA integrity_check(1)').fetchall() != [('ok',)]:
            raise ValueError('database integrity check failed')
        if db.execute('PRAGMA page_count').fetchone()[0] * db.execute('PRAGMA page_size').fetchone()[0] > MAX_BYTES:
            raise ValueError('database too large')
        return db
    except BaseException:
        db.close()
        raise


def backup(source, destination, *, expected_sha256=None):
    """Create a new backup (or rehearsal copy with expected hash); never overwrite.
    A successful copy is not authorization to resume operations.
    """
    source, destination = private_path(source), private_path(destination)
    if os.path.lexists(destination):
        raise FileExistsError(destination)
    before = source_stat(source)
    original_hash = digest(source)
    if expected_sha256 is not None and (not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256) or expected_sha256 != original_hash):
        raise ValueError('source hash mismatch')
    deadline = time.monotonic() + MAX_SECONDS
    fd, name = tempfile.mkstemp(prefix='.research-backup-', dir=destination.parent)
    os.close(fd)
    tmp = Path(name)
    try:
        def progress(status, remaining, total):
            if time.monotonic() > deadline:
                raise TimeoutError('backup deadline exceeded')
        with closing(inspect(source, deadline)) as src, closing(sqlite3.connect(tmp, timeout=1)) as dst:
            src.backup(dst, pages=128, progress=progress, sleep=0.05)
        source_stat(tmp)
        with closing(inspect(tmp, deadline)):
            pass
        result_hash = digest(tmp)
        if source_stat(source) != before or digest(source) != original_hash:
            raise ValueError('source changed during backup')
        if time.monotonic() > deadline:
            raise TimeoutError('backup deadline exceeded')
        with tmp.open('rb') as stream:
            os.fsync(stream.fileno())
        os.link(tmp, destination)  # atomic no-overwrite publication in trusted directory
        tmp.unlink()
        fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return {'schema':'research-db-backup-v1','integrity_check':'PASS','source_sha256':original_hash,'backup_sha256':result_hash,'bytes':destination.stat().st_size,'status':'HOLD','model_input_allowed':False,'live_trading':'DISABLED','production_recommendations':'DISABLED','automatic_restore':False,'rollback_protection':False}
    finally:
        for suffix in ('', '-journal', '-wal', '-shm'):
            Path(str(tmp)+suffix).unlink(missing_ok=True)


if __name__ == '__main__':
    import argparse
    import json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('source', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--expected-sha256')
    a = p.parse_args()
    print(json.dumps(backup(a.source, a.destination, expected_sha256=a.expected_sha256), sort_keys=True))
