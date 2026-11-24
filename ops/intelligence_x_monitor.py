"""Read-only monitor for frozen halted recovery artifacts, never a live worker gate."""
import hashlib
import hmac
import os
import re
import sqlite3
import stat
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024


def _fingerprint(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


class HaltedMonitor:
    """Pin independently retained digest; sticky in-process quarantine on any failure."""
    def __init__(self, path, *, expected_sha256):
        if type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
            raise ValueError('INVALID_PIN')
        self._path = Path(path).absolute()
        self._digest = expected_sha256
        self._identity = None
        self._quarantine = None

    def _inspect(self):
        p = self._path
        if any(os.path.lexists(str(p) + s) for s in ('-wal', '-shm', '-journal')):
            raise ValueError('SIDECAR_PRESENT')
        fd = os.open(p, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as f:
            before = os.fstat(f.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
                raise ValueError('UNSAFE_FILE')
            data = f.read(MAX_BYTES + 1)
            after = os.fstat(f.fileno())
        if (_fingerprint(before) != _fingerprint(after) or
                _fingerprint(after) != _fingerprint(p.lstat()) or len(data) != before.st_size):
            raise ValueError('FILE_CHANGED')
        identity = (before.st_dev, before.st_ino)
        if self._identity is not None and identity != self._identity:
            raise ValueError('FILE_REPLACED')
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), self._digest):
            raise ValueError('DIGEST_MISMATCH')
        if data[:16] != b'SQLite format 3\x00' or data[18:20] != b'\x01\x01':
            raise ValueError('UNSUPPORTED_FORMAT')
        conn = sqlite3.connect(':memory:')
        try:
            conn.deserialize(data)
            conn.execute('PRAGMA trusted_schema=OFF')
            if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                raise ValueError('INTEGRITY_FAILURE')
            if conn.execute('SELECT id FROM emergency_stop').fetchall() != [(1,)]:
                raise ValueError('HALT_MISSING')
            if conn.execute("SELECT COUNT(*) FROM jobs WHERE state='LEASED' OR token IS NOT NULL").fetchone()[0]:
                raise ValueError('ACTIVE_LEASE')
        finally:
            conn.close()
        self._identity = identity

    def sample(self):
        if self._quarantine is None:
            try:
                self._inspect()
            except ValueError as exc:
                self._quarantine = str(exc)
            except (OSError, sqlite3.Error, AttributeError):
                self._quarantine = 'READ_OR_RUNTIME_FAILURE'
        return {'quarantined': self._quarantine is not None,
                'reason': self._quarantine or 'PINNED_HALTED_SNAPSHOT',
                'status': 'HOLD', 'production_recommendations': 'DISABLED'}


def orphan_candidates(directory):
    """List names only; no automatic deletion or assertion a writer is dead."""
    p = Path(directory)
    root = p.lstat()
    if not stat.S_ISDIR(root.st_mode) or root.st_uid != os.getuid() or root.st_mode & 0o077:
        raise ValueError('PRIVATE_DIRECTORY_REQUIRED')
    names = []
    for i, child in enumerate(p.iterdir()):
        if i >= 10000:
            raise ValueError('DIRECTORY_LIMIT')
        if not re.fullmatch(r'\.halted-recovery-[a-z0-9_]{8}', child.name):
            continue
        s = child.lstat()
        if stat.S_ISREG(s.st_mode) and s.st_uid == os.getuid() and s.st_nlink == 1 and not s.st_mode & 0o077:
            names.append(child.name)
    return sorted(names)
