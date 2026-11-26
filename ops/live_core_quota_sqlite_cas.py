"""Durable single-host CAS implementation for the existing simulated quota contract.

All callers must use one private local SQLite database. No network permission,
cross-host consensus, backup rollback protection or provider quota attestation.
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from vnext_quota_coordinator_contract import State, valid
from vnext_quota_ledger_offline import ID


def encode(state):
    return json.dumps([state.epoch,state.revision,state.clock,state.attempts],
                      separators=(",",":"),allow_nan=False)


def decode(raw):
    epoch,revision,clock,attempts=json.loads(raw)
    state=State(epoch,revision,clock,tuple(tuple(r) for r in attempts))
    if not valid(state,epoch,0) or encode(state)!=raw:
        raise ValueError("INVALID_STORED_STATE")
    return state


class SQLiteCAS:
    def __init__(self,path,epoch):
        if type(epoch) is not str or not ID.fullmatch(epoch):
            raise ValueError("BAD_EPOCH")
        self.path=Path(path).resolve()
        self.epoch=epoch

    def initialize(self):
        # Refuse existing database, including damaged or rolled-back copies.
        with self.path.open("xb"):
            pass
        with closing(sqlite3.connect(self.path,timeout=5)) as db, db:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE quota (singleton INTEGER PRIMARY KEY CHECK(singleton=1), raw TEXT NOT NULL)")
            db.execute("INSERT INTO quota VALUES(1,?)",(encode(State(self.epoch,0,0,())),))

    def connect(self):
        db=sqlite3.connect(self.path.resolve(strict=True).as_uri()+"?mode=rw",
                           uri=True,timeout=5,isolation_level=None)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def current(self,db):
        row=db.execute("SELECT raw FROM quota WHERE singleton=1").fetchone()
        if row is None:
            raise ValueError("MISSING_STATE")
        state=decode(row[0])
        if state.epoch!=self.epoch:
            raise ValueError("EPOCH_MISMATCH")
        return state

    def read(self):
        with closing(self.connect()) as db:
            return self.current(db)

    def cas(self,old,new):
        if not valid(old,self.epoch,0) or not valid(new,self.epoch,0):
            raise ValueError("BAD_STATE")
        if (new.revision!=old.revision+1 or new.clock<old.clock
            or len(new.attempts)!=len(old.attempts)+1
            or new.attempts[:-1]!=old.attempts or new.attempts[-1][2]!=new.clock):
            raise ValueError("NON_APPEND_TRANSITION")
        with closing(self.connect()) as db:
            db.execute("BEGIN IMMEDIATE")
            if self.current(db)!=old:
                db.rollback()
                return False
            db.execute("UPDATE quota SET raw=? WHERE singleton=1",(encode(new),))
            db.commit()
            return True
