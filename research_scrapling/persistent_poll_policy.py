"""Local SQLite coordination for simulated polling; no network or activation.
All workers must share one local database and comparable nondecreasing clock.
An abandoned lease stays blocked until reviewed; never auto-reissue it.
"""
import json
import os
import sqlite3
from dataclasses import asdict
from pathlib import Path
from poll_policy import PollPolicy, _Scope


class PersistentPollPolicy:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @classmethod
    def initialize(cls, path, scopes):
        scopes = tuple(scopes)
        if not scopes or len(set(scopes)) != len(scopes) or any(not isinstance(s, str) or not s or len(s) > 128 for s in scopes):
            raise ValueError("invalid scopes")
        store = cls(path)
        fd = os.open(store.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with store._connect() as db:
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
        doc = json.loads(raw)
        if doc["schema"] != 1 or not doc["scopes"]:
            raise ValueError("unknown or empty policy")
        p = PollPolicy(doc["scopes"])
        p._time(doc["clock"])
        if type(doc["serial"]) is not int or doc["serial"] < 0:
            raise ValueError("invalid serial")
        p._serial = doc["serial"]
        for key, value in doc["scopes"].items():
            if value["lease"] is not None:
                value["lease"] = tuple(value["lease"])
            p._scopes[key] = _Scope(**value)
        return p

    def _operation(self, method, *args):
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM policy WHERE id=1").fetchone()
            if row is None:
                raise ValueError("missing policy state")
            p = self._decode(row[0])
            result = getattr(p, method)(*args)
            db.execute("UPDATE policy SET state=? WHERE id=1", (self._encode(p),))
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
