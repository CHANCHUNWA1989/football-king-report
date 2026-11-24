"""Offline recovery into a new, permanently halted journal; no resume API."""
import hashlib
import hmac
import os
import re
import sqlite3
import tempfile
from pathlib import Path

MAX_BYTES = 32 * 1024 * 1024
SCHEMA = {
    ('table', 'jobs', 'jobs', 'CREATE TABLE jobs (job TEXT PRIMARY KEY, state TEXT NOT NULL, attempt INTEGER NOT NULL, token TEXT, deadline INTEGER NOT NULL, last_seen INTEGER NOT NULL)'),
    ('table', 'emergency_stop', 'emergency_stop', 'CREATE TABLE emergency_stop (id INTEGER PRIMARY KEY CHECK(id=1))'),
    ('index', 'sqlite_autoindex_jobs_1', 'jobs', None),
}


def _sidecars(p):
    return any(os.path.lexists(str(p) + s) for s in ('-wal', '-shm', '-journal'))


def _validate(conn):
    if set(conn.execute('SELECT type,name,tbl_name,sql FROM sqlite_schema')) != SCHEMA:
        raise ValueError('UNSUPPORTED_SCHEMA')
    if conn.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('INTEGRITY_FAILURE')
    if conn.execute('SELECT id FROM emergency_stop').fetchall() not in ([], [(1,)]):
        raise ValueError('INVALID_HALT_STATE')
    rows = conn.execute('SELECT job,state,attempt,token,deadline,last_seen FROM jobs').fetchmany(10001)
    if len(rows) > 10000:
        raise ValueError('INVALID_CAPACITY')
    for job, state, attempt, token, deadline, seen in rows:
        if not (type(job) is str and re.fullmatch('[0-9a-f]{64}', job)
                and state in ('LEASED', 'DONE', 'STOPPED')
                and type(attempt) is int and 0 <= attempt <= 3
                and type(deadline) is int and 0 <= deadline <= 4102444860
                and type(seen) is int and 0 <= seen <= 4102444800
                and ((state == 'LEASED' and attempt >= 1 and type(token) is str
                      and re.fullmatch('[0-9a-f]{32}', token))
                     or (state != 'LEASED' and token is None))):
            raise ValueError('INVALID_JOB_STATE')
    return len(rows)


def recover_halted(source, destination, *, expected_sha256):
    """Use an independently retained digest of a frozen rollback-mode backup.

    Trusted private directory, no concurrent source/destination writers. Never
    replace an existing journal. A digest does not establish backup freshness.
    """
    if type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('INVALID_EXPECTED_DIGEST')
    src, dst = Path(source), Path(destination)
    if os.path.lexists(dst) or _sidecars(dst) or _sidecars(src):
        raise ValueError('UNSAFE_PATH_OR_SIDECAR')
    with src.open('rb') as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or _sidecars(src):
        raise ValueError('UNSAFE_BACKUP')
    if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected_sha256):
        raise ValueError('DIGEST_MISMATCH')
    if data[:16] != b'SQLite format 3\x00' or data[18:20] != b'\x01\x01':
        raise ValueError('UNSUPPORTED_BACKUP_FORMAT')
    conn = sqlite3.connect(':memory:')
    try:
        conn.deserialize(data)
        conn.execute('PRAGMA trusted_schema=OFF')
        count = _validate(conn)
        with conn:
            conn.execute('INSERT OR IGNORE INTO emergency_stop VALUES (1)')
            conn.execute("UPDATE jobs SET state='STOPPED',token=NULL WHERE state='LEASED'")
        _validate(conn)
        if conn.execute('SELECT id FROM emergency_stop').fetchall() != [(1,)] or conn.execute("SELECT COUNT(*) FROM jobs WHERE state='LEASED'").fetchone()[0]:
            raise ValueError('HALT_VERIFICATION_FAILED')
        recovered = conn.serialize()
    finally:
        conn.close()
    # Publish only complete halted bytes. Hard link never overwrites a target.
    fd, tmp = tempfile.mkstemp(prefix='.halted-recovery-', dir=dst.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(recovered)
            f.flush()
            os.fsync(f.fileno())
        if _sidecars(dst):
            raise ValueError('UNSAFE_PATH_OR_SIDECAR')
        os.link(tmp, dst)
    finally:
        os.unlink(tmp)
    return {'halted': True, 'total': count, 'status': 'HOLD',
            'production_recommendations': 'DISABLED'}
