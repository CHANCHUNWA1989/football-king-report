"""Offline, single-host quota reservation rehearsal; never authorizes HTTP.
One pre-provisioned private SQLite database per provider account. All simulated
consumers must share it. No cross-runner, provider quota or clock authentication.
A reserved attempt is never refunded, even on failure. No network or secrets.
"""
import re
import sqlite3
from contextlib import closing

ID = re.compile(r"[A-Za-z0-9_-]{1,80}", re.ASCII)


def initialize(path):
    """Explicit research setup; do not call during reservation or auto-recover loss."""
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, consumer TEXT NOT NULL, ts INTEGER NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS attempt_ts ON attempts(ts)")
        db.execute("CREATE TABLE IF NOT EXISTS clock (singleton INTEGER PRIMARY KEY CHECK(singleton=1), ts INTEGER NOT NULL)")
        db.execute("INSERT OR IGNORE INTO clock VALUES (1,0)")


def result(reason, reserved=False):
    return {"reason": reason, "simulated_reservation": reserved,
            "real_request_authorized": False, "production_recommendations": "DISABLED",
            "status": "HOLD"}


def reserve(path, *, request_id, consumer, now, observed, daily_remaining, minute_remaining):
    """Atomic same-host rolling limits plus conservative declared quota bound.
    Epoch integer seconds are injected for deterministic offline research.
    Even a successful result does not permit a real provider request.
    """
    if not all(type(v) is str and ID.fullmatch(v) for v in (request_id, consumer)):
        return result("BAD_ID")
    if not all(type(v) is int for v in (now, observed, daily_remaining, minute_remaining)):
        return result("BAD_EVIDENCE")
    if not (0 < observed <= now <= 253402300799 and now-observed <= 300
            and 2 <= daily_remaining <= 100 and 2 <= minute_remaining <= 10):
        return result("BAD_EVIDENCE")
    from pathlib import Path
    try:
        uri = Path(path).resolve(strict=True).as_uri() + "?mode=rw"
        with closing(sqlite3.connect(uri, uri=True, timeout=5, isolation_level=None)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT ts FROM clock WHERE singleton=1").fetchone()
            if row is None or type(row[0]) is not int or row[0] < 0:
                db.rollback()
                return result("INVALID_LEDGER")
            if now < row[0]:
                db.rollback()
                return result("CLOCK_ROLLBACK")
            db.execute("UPDATE clock SET ts=? WHERE singleton=1", (now,))
            if db.execute("SELECT 1 FROM attempts WHERE id=?", (request_id,)).fetchone():
                db.commit()
                return result("REPLAY")
            def count_since(start):
                return db.execute("SELECT COUNT(*) FROM attempts WHERE ts>=?", (start,)).fetchone()[0]
            # Include the boundary second conservatively; no reliance on reset time.
            day = count_since(now-86400)
            minute = count_since(now-60)
            after = count_since(observed)
            if day >= 99 or minute >= 9 or after >= min(daily_remaining, minute_remaining)-1:
                db.commit()
                return result("QUOTA_RESERVE")
            db.execute("INSERT INTO attempts VALUES (?,?,?)", (request_id, consumer, now))
            db.commit()
            return result("SIMULATED_ONLY", True)
    except (sqlite3.Error, OSError, ValueError, TypeError, RuntimeError):
        return result("LEDGER_UNAVAILABLE")
