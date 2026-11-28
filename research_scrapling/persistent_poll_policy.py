"""Local SQLite coordination for simulated polling; no network or activation.
All workers must share one local database and comparable nondecreasing clock.
An abandoned lease stays blocked until reviewed; never auto-reissue it.
"""
from contextlib import closing
import json
from math import isfinite
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from poll_policy import PollPolicy, _Scope


MAX_STATE_BYTES = 1_000_000
MAX_SCOPES = 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate state key")
        result[key] = value
    return result


def valid_time(value):
    return type(value) in (int, float) and 0 <= value <= 1e15 and isfinite(value)


def valid_revision(value):
    return value is None or (isinstance(value, str) and 0 < len(value) <= 256)


class PersistentPollPolicy:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @classmethod
    def initialize(cls, path, scopes):
        scopes = tuple(scopes)
        if not 1 <= len(scopes) <= MAX_SCOPES or any(not isinstance(s, str) or not s or len(s) > 128 for s in scopes) or len(set(scopes)) != len(scopes):
            raise ValueError("invalid scopes")
        store = cls(path)
        fd = os.open(store.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(store._connect()) as db, db:
            db.execute("CREATE TABLE policy (id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL)")
            db.execute("INSERT INTO policy VALUES (1, ?)", (store._encode(PollPolicy(scopes)),))
        return store

    def _connect(self):
        # Never silently recreate missing state after a crash or deletion.
        return sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=5)

    @staticmethod
    def _encode(p):
        return json.dumps({"schema": 1, "clock": p._clock, "serial": p._serial,
                           "scopes": {k: asdict(v) for k, v in p._scopes.items()}},
                          sort_keys=True, allow_nan=False)

    @staticmethod
    def _decode(raw):
        if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_STATE_BYTES:
            raise ValueError("invalid state size")
        doc = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(doc, dict) or set(doc) != {"schema", "clock", "serial", "scopes"}:
            raise ValueError("invalid state schema")
        if type(doc["schema"]) is not int or doc["schema"] != 1 or not valid_time(doc["clock"]):
            raise ValueError("invalid state version or clock")
        scopes = doc["scopes"]
        if not isinstance(scopes, dict) or not 1 <= len(scopes) <= MAX_SCOPES:
            raise ValueError("invalid scopes")
        p = PollPolicy(scopes)
        p._time(doc["clock"])
        if type(doc["serial"]) is not int or doc["serial"] < 0:
            raise ValueError("invalid serial")
        p._serial = doc["serial"]
        seen_leases = set()
        for key, value in scopes.items():
            if not key or len(key) > 128 or not isinstance(value, dict) or set(value) != set(asdict(_Scope())):
                raise ValueError("invalid scope schema")
            if not valid_time(value["due"]) or type(value["failures"]) is not int or not 0 <= value["failures"] <= 7 or type(value["halted"]) is not bool:
                raise ValueError("invalid scope state")
            if not all(valid_revision(value[k]) for k in ("cached_revision", "pending_revision")):
                raise ValueError("invalid revision")
            lease = value["lease"]
            if lease is not None:
                if not isinstance(lease, list) or len(lease) != 2 or type(lease[0]) is not int or not 1 <= lease[0] <= p._serial or lease[0] in seen_leases or lease[1] not in ("revision", "payload") or value["halted"]:
                    raise ValueError("invalid lease")
                if (lease[1] == "payload") != (value["pending_revision"] is not None):
                    raise ValueError("lease revision mismatch")
                seen_leases.add(lease[0])
                value["lease"] = tuple(lease)
            p._scopes[key] = _Scope(**value)
        return p

    def _operation(self, method, *args):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM policy WHERE id=1 AND length(CAST(state AS BLOB)) <= ?", (MAX_STATE_BYTES,)).fetchone()
            if row is None:
                raise ValueError("missing policy state")
            p = self._decode(row[0])
            result = getattr(p, method)(*args)
            encoded = self._encode(p)
            self._decode(encoded)  # Never commit an invalid next state.
            db.execute("UPDATE policy SET state=? WHERE id=1", (encoded,))
            db.commit()
            return result
        finally:
            db.close()

    def reserve(self, scope, now):
        return self._operation("reserve", scope, now)

    def finish(self, scope, lease, now, status, revision=None, retry_after=0):
        return self._operation("finish", scope, lease, now, status, revision, retry_after)

    def snapshot(self, scope):
        return self._operation("snapshot", scope)
