"""Bounded local research fixture cache; no network, raw provider archiving or model use.
Only a single host, with a common trusted nondecreasing clock, is supported.
A digest detects accidental corruption, not malicious writers or database rollback.
"""
from contextlib import closing
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from persistent_poll_policy import valid_time, valid_revision

MAX_BYTES = 65536
MAX_SCOPES = 128
TTL = 300


def digest(scope, revision, captured, body):
    header = json.dumps([scope, revision, captured], separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(header + b'\0' + body).hexdigest()


class ResearchCache:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @classmethod
    def initialize(cls, path, scopes):
        scopes = tuple(scopes)
        if not 1 <= len(scopes) <= MAX_SCOPES or any(not isinstance(x, str) or not x or len(x) > 128 for x in scopes) or len(set(scopes)) != len(scopes):
            raise ValueError('invalid scopes')
        cache = cls(path)
        fd = os.open(cache.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(cache._connect()) as db, db:
            db.execute('CREATE TABLE clock (id INTEGER PRIMARY KEY CHECK(id=1), seen REAL NOT NULL)')
            db.execute('INSERT INTO clock VALUES (1, 0)')
            db.execute('CREATE TABLE cache (scope TEXT PRIMARY KEY, revision TEXT, captured REAL, body BLOB, sha TEXT)')
            db.executemany('INSERT INTO cache(scope) VALUES (?)', [(s,) for s in scopes])
        return cache

    def _connect(self):
        return sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)

    def _operate(self, scope, now, revision, body=None):
        if not isinstance(scope, str) or not scope or len(scope) > 128 or revision is None or not valid_revision(revision) or not valid_time(now):
            raise ValueError('invalid request')
        if body is not None and (type(body) is not bytes or not 0 < len(body) <= MAX_BYTES):
            raise ValueError('invalid body')
        now = float(now)
        db = self._connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            clock = db.execute('SELECT seen FROM clock WHERE id=1').fetchone()
            if clock is None or not valid_time(clock[0]) or now < clock[0]:
                raise ValueError('invalid clock')
            row = db.execute('SELECT revision,captured,body,sha FROM cache WHERE scope=? AND (body IS NULL OR length(body)<=?)', (scope, MAX_BYTES)).fetchone()
            if row is None:
                raise ValueError('unknown scope or oversized state')
            old, captured, previous, sha = row
            if old is None:
                if any(x is not None for x in row):
                    raise ValueError('invalid empty entry')
            elif not valid_revision(old) or not valid_time(captured) or captured > clock[0] or type(previous) is not bytes or not 0 < len(previous) <= MAX_BYTES or sha != digest(scope, old, captured, previous):
                raise ValueError('corrupt entry')
            result = {'status':'HOLD','live_trading':'DISABLED','production_recommendations':'DISABLED','model_input_allowed':False,'network_enabled':False,'fresh_evidence':False,'cache_state':'MISS','body':None}
            if body is not None:
                if old == revision:
                    if previous != body:
                        raise ValueError('same revision content conflict')
                    result['cache_state'] = 'UNCHANGED_NO_REFRESH'
                else:
                    db.execute('UPDATE cache SET revision=?,captured=?,body=?,sha=? WHERE scope=?', (revision,now,body,digest(scope,revision,now,body),scope))
                    result['cache_state'] = 'STORED_RESEARCH_ONLY'
            elif old == revision:
                if now - captured <= TTL:
                    result.update(cache_state='HIT_RESEARCH_ONLY',body=previous,captured=captured,sha256=sha)
                else:
                    result['cache_state'] = 'EXPIRED'
            db.execute('UPDATE clock SET seen=? WHERE id=1', (now,))
            db.commit()
            return result
        finally:
            db.close()

    def put(self, scope, revision, body, now):
        if body is None:
            raise ValueError('body required')
        return self._operate(scope, now, revision, body)

    def get(self, scope, revision, now):
        return self._operate(scope, now, revision)
