"""V2.1 local durable research queue. Only the fixed read-only hub is executable."""
import argparse
import contextlib
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import sqlite3
import stat
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
SKILL = Path(__file__).resolve().parent
MAX_ATTEMPTS = 3
MAX_OUTPUT = 2 * 1024 * 1024
FLAGS = dict(release="HOLD", production_recommendations="DISABLED",
             canPromote=False, mergeAuthorized=False, automaticProductionRepair=False)
DB = "queue.sqlite3"

def _key(key):
    if not isinstance(key, str) or not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("INVALID_TASK_ID")
    return key

def _path(directory, existing=True):
    p = Path(directory).absolute()
    if p != p.resolve() or p == ROOT or ROOT in p.parents:
        raise ValueError("STATE_MUST_BE_OUTSIDE_REPO_NO_SYMLINK")
    if existing:
        s = p.stat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
            raise ValueError("STATE_DIRECTORY_NOT_PRIVATE")
        for name in (DB, DB+"-journal", DB+"-wal", DB+"-shm"):
            f = p / name
            try:
                s = f.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(s.st_mode):
                raise ValueError("STATE_SYMLINK")
            if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1:
                raise ValueError("STATE_FILE_UNSAFE")
        if not (p/DB).is_file():
            raise ValueError("STATE_NOT_INITIALIZED")
    return p

def init(directory):
    p = _path(directory, False)
    p.mkdir(mode=0o700)
    with contextlib.closing(sqlite3.connect(p/DB)) as db:
        db.executescript("""
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=FULL;
        CREATE TABLE control (id INTEGER PRIMARY KEY CHECK(id=1), stopped INTEGER NOT NULL CHECK(stopped IN(0,1)));
        INSERT INTO control VALUES(1,0);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL CHECK(status IN('PENDING','RUNNING','RETRY_WAIT','SUCCEEDED','BLOCKED')),
        attempts INTEGER NOT NULL CHECK(attempts BETWEEN 0 AND 3), due INTEGER NOT NULL,
        token TEXT, outcome TEXT);
        """)
        db.commit()
    os.chmod(p/DB, 0o600)

@contextlib.contextmanager
def _tx(directory):
    p = _path(directory)
    with contextlib.closing(sqlite3.connect(p/DB, timeout=10, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        try:
            yield db
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise

def _stopped(db):
    row=db.execute("SELECT stopped FROM control WHERE id=1").fetchone()
    if row is None or row[0] not in (0,1):
        raise ValueError("INVALID_CONTROL")
    return bool(row[0])

def enqueue(directory, key, *, now):
    _key(key)
    with _tx(directory) as db:
        if _stopped(db):
            return False
        return db.execute("INSERT OR IGNORE INTO jobs VALUES(?, 'PENDING',0,?,NULL,NULL)", (key, now)).rowcount == 1

def claim(directory, key, *, now):
    _key(key)
    with _tx(directory) as db:
        if _stopped(db) or db.execute("SELECT 1 FROM jobs WHERE status='RUNNING'").fetchone():
            return None
        token = secrets.token_hex(16)
        n = db.execute("""UPDATE jobs SET status='RUNNING',attempts=attempts+1,token=?
            WHERE id=? AND status IN('PENDING','RETRY_WAIT') AND due<=? AND attempts<?""",
            (token,key,now,MAX_ATTEMPTS)).rowcount
        return token if n == 1 else None

def finish(directory, key, token, outcome, *, now):
    _key(key)
    if outcome not in ("SUCCESS","TRANSIENT","PERMANENT") or not token:
        raise ValueError("INVALID_OUTCOME")
    with _tx(directory) as db:
        row = db.execute("SELECT attempts FROM jobs WHERE id=? AND status='RUNNING' AND token=?", (key,token)).fetchone()
        if not row:
            raise ValueError("CLAIM_TOKEN_MISMATCH")
        attempt=row[0]
        status = "SUCCEEDED" if outcome=="SUCCESS" else "BLOCKED"
        due=now
        if outcome=="TRANSIENT" and attempt<MAX_ATTEMPTS and not _stopped(db):
            status="RETRY_WAIT"
            due=now+2**attempt
        db.execute("UPDATE jobs SET status=?,due=?,token=NULL,outcome=? WHERE id=?", (status,due,outcome,key))

def stop(directory):
    with _tx(directory) as db:
        db.execute("UPDATE control SET stopped=1 WHERE id=1")

def snapshot(directory):
    with _tx(directory) as db:
        return dict(**FLAGS, stopped=_stopped(db), jobs=[dict(r) for r in db.execute(
            "SELECT id,status,attempts,due,outcome FROM jobs ORDER BY id")])

def fingerprint():
    # Include every existing skill implementation/fixture plus three input snapshots.
    paths = sorted([p for p in SKILL.iterdir() if p.is_file() and p.suffix in (".mjs",".py",".json",".md")]+
        [ROOT/"sources/seven_quality_gates_latest.json",ROOT/"market/latest.json",ROOT/"evidence/settled.json"])
    h=hashlib.sha256(b"football-king-research-hub-v2.1\0")
    for p in paths:
        h.update(str(p.relative_to(ROOT)).encode()+b"\0")
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()

def classify(code, raw):
    if code != 0 or len(raw)>MAX_OUTPUT:
        return "PERMANENT"
    try:
        r=json.loads(raw)
        if (isinstance(r,dict) and r.get("status")=="RESEARCH_COMPLETE"
            and type(r.get("completed")) is int and r["completed"]==8
            and type(r.get("checksPassed")) is int and r["checksPassed"]==124
            and r.get("inputsUnchanged") is True and r.get("diagnosticHashesMatch") is True
            and all(r.get(k) is v if isinstance(v,bool) else r.get(k)==v for k,v in FLAGS.items())):
            return "SUCCESS"
    except (ValueError,TypeError,UnicodeError):
        pass
    return "PERMANENT"

def execute_hub():
    node=shutil.which("node")
    if not node:
        return "PERMANENT"
    # Fixed arguments, minimal environment, no provider credentials or network calls.
    with tempfile.TemporaryFile() as out:
        try:
            p=subprocess.Popen([node,str(SKILL/"hub.mjs"),"--run"],cwd=ROOT,
                env={"LANG":"C.UTF-8"},stdout=out,stderr=subprocess.DEVNULL,start_new_session=True)
        except OSError as exc:
            return "TRANSIENT" if exc.errno in (errno.EAGAIN,errno.ETXTBSY) else "PERMANENT"
        try:
            p.wait(timeout=150)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(p.pid,signal.SIGKILL)
                p.wait(timeout=10)
            except (OSError,subprocess.TimeoutExpired):
                return "PERMANENT"
            # Timeout is deliberately permanent: no proof all grandchildren stopped.
            return "PERMANENT"
        out.seek(0)
        return classify(p.returncode,out.read(MAX_OUTPUT+1))

def run_once(directory):
    key=fingerprint()
    token=claim(directory,key,now=int(time.time()))
    if token is None:
        return "NO_CLAIM"
    # A crashed worker leaves RUNNING; no automatic reclaim or duplicate execution.
    try:
        if snapshot(directory)["stopped"] or fingerprint()!=key:
            outcome="PERMANENT"
        else:
            outcome=execute_hub()
            if fingerprint()!=key:
                outcome="PERMANENT"
    except Exception:
        outcome="PERMANENT"
    finish(directory,key,token,outcome,now=int(time.time()))
    return outcome

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["init","enqueue","run","status","stop"])
    p.add_argument("directory",type=Path)
    a=p.parse_args()
    try:
        result={}
        if a.command=="init": init(a.directory)
        elif a.command=="enqueue": result["enqueued"]=enqueue(a.directory,fingerprint(),now=int(time.time()))
        elif a.command=="run": result["runOutcome"]=run_once(a.directory)
        elif a.command=="stop": stop(a.directory)
        print(json.dumps(dict(**snapshot(a.directory),**result),sort_keys=True))
        return 1 if result.get("runOutcome")=="PERMANENT" else 0
    except (OSError,ValueError,sqlite3.Error):
        print(json.dumps(dict(**FLAGS,error="QUEUE_BLOCKED")))
        return 1

if __name__=="__main__":
    raise SystemExit(main())
