"""Offline SQLite lease journal. No task execution, network, or authorization."""
import re
import secrets
import sqlite3
import shutil
from pathlib import Path
from contextlib import contextmanager

LEASE_SECONDS = 60
MAX_ATTEMPTS = 3
MAX_JOBS = 10000


@contextmanager
def _db(path):
    conn = sqlite3.connect(path, timeout=2, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("CREATE TABLE IF NOT EXISTS jobs (job TEXT PRIMARY KEY, "
                     "state TEXT NOT NULL, attempt INTEGER NOT NULL, token TEXT, "
                     "deadline INTEGER NOT NULL, last_seen INTEGER NOT NULL)")
        conn.execute("CREATE TABLE IF NOT EXISTS emergency_stop (id INTEGER PRIMARY KEY CHECK(id=1))")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _check(job, now):
    if type(job) is not str or not re.fullmatch(r"[0-9a-f]{64}", job):
        raise ValueError("INVALID_JOB_ID")
    if type(now) is not int or not 0 <= now <= 4102444800:
        raise ValueError("INVALID_CLOCK")


def _read(conn, job, now):
    row = conn.execute("SELECT state, attempt, token, deadline, last_seen "
                       "FROM jobs WHERE job=?", (job,)).fetchone()
    if row and now < row[4]:
        raise ValueError("CLOCK_ROLLBACK")
    if row:
        conn.execute("UPDATE jobs SET last_seen=? WHERE job=?", (now, job))
    return row


def _ensure_capacity(conn):
    if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] >= MAX_JOBS:
        raise ValueError("JOURNAL_CAPACITY_EXCEEDED")


def _halted(conn):
    return conn.execute("SELECT 1 FROM emergency_stop WHERE id=1").fetchone() is not None


def halt_all(path):
    """Permanently halt this journal; no reset API or external worker cancellation."""
    with _db(path) as conn:
        conn.execute("INSERT OR IGNORE INTO emergency_stop VALUES (1)")
        conn.execute("UPDATE jobs SET state='STOPPED', token=NULL WHERE state='LEASED'")


def resource_snapshot(path):
    """Read-only local snapshot; no job tokens or identities returned."""
    p = Path(path).resolve(strict=True)
    conn = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True, timeout=2)
    try:
        conn.execute('BEGIN')
        halted = _halted(conn)
        counts = dict(conn.execute('SELECT state, COUNT(*) FROM jobs GROUP BY state'))
        if not set(counts) <= {'LEASED', 'DONE', 'STOPPED'}:
            raise ValueError('INVALID_STATE')
        total = sum(counts.values())
        free = shutil.disk_usage(p.parent).free
        return {'halted': halted, 'total': total, 'leased': counts.get('LEASED', 0),
                'done': counts.get('DONE', 0), 'stopped': counts.get('STOPPED', 0),
                'capacity_warning': total * 10 >= MAX_JOBS * 8,
                'disk_free_bytes': free, 'disk_warning': free < 100 * 1024 * 1024,
                'status': 'HOLD', 'production_recommendations': 'DISABLED'}
    finally:
        conn.close()


def claim(path, job, *, now):
    """Return a local lease or None; expired work may be reclaimed, never replayed here."""
    _check(job, now)
    with _db(path) as conn:
        if _halted(conn):
            return None
        row = _read(conn, job, now)
        if row:
            state, attempt, _, deadline, _ = row
            if state in ("DONE", "STOPPED") or now < deadline:
                return None
            if attempt >= MAX_ATTEMPTS:
                conn.execute("UPDATE jobs SET state='STOPPED', token=NULL, last_seen=? "
                             "WHERE job=?", (now, job))
                return None
        else:
            _ensure_capacity(conn)
            attempt = 0
        token = secrets.token_hex(16)
        deadline = now + LEASE_SECONDS
        conn.execute("INSERT OR REPLACE INTO jobs VALUES (?, 'LEASED', ?, ?, ?, ?)",
                     (job, attempt + 1, token, deadline, now))
        return {"token": token, "attempt": attempt + 1, "deadline": deadline,
                "status": "HOLD", "production_recommendations": "DISABLED"}


def finish(path, job, *, token, now):
    """Only the current unexpired lease can mark a synthetic task completed."""
    _check(job, now)
    if type(token) is not str or not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("INVALID_LEASE")
    with _db(path) as conn:
        if _halted(conn):
            return False
        row = _read(conn, job, now)
        if not row or row[0] != "LEASED" or row[2] != token or now >= row[3]:
            return False
        conn.execute("UPDATE jobs SET state='DONE', token=NULL, last_seen=? WHERE job=?",
                     (now, job))
        return True


def stop(path, job, *, now):
    """Persist a terminal stop, including for a job that has not yet started."""
    _check(job, now)
    with _db(path) as conn:
        row = _read(conn, job, now)
        if row and row[0] in ("DONE", "STOPPED"):
            return False
        if row is None:
            _ensure_capacity(conn)
        conn.execute("INSERT OR REPLACE INTO jobs VALUES (?, 'STOPPED', ?, NULL, 0, ?)",
                     (job, row[1] if row else 0, now))
        return True
