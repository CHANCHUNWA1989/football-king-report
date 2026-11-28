"""V3.1 portable, bounded research-state checkpoint. No external trust or uptime claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import time
import research_queue as q
import research_scheduler as s

FLAGS=dict(**s.FLAGS,deploymentAuthorized=False)
SCHEMA="football-king-research-checkpoint-v1"
MAX_BYTES=2*1024*1024
MAX_ROWS=4096
def require(ok,reason):
    if not ok: raise ValueError(reason)
def integer(v):
    return type(v) is int and v>=0
def exact(v,keys):
    return isinstance(v,dict) and set(v)==set(keys)
def canonical(d):
    return (json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False)+"\n").encode()
def validate(d):
    require(exact(d,["schema","release","production_recommendations","stopped","jobs","cycles"]) and d["schema"]==SCHEMA and d["release"]=="HOLD" and d["production_recommendations"]=="DISABLED" and type(d["stopped"]) is bool,"CHECKPOINT_SCHEMA")
    jobs,cycles=d["jobs"],d["cycles"]
    require(isinstance(jobs,list) and isinstance(cycles,list) and len(jobs)<=MAX_ROWS and len(cycles)<=MAX_ROWS,"CHECKPOINT_LIMIT")
    keys=set()
    for j in jobs:
        require(exact(j,["id","status","attempts","due","outcome"]),"JOB_SCHEMA")
        q._key(j["id"])
        require(j["id"] not in keys and integer(j["attempts"]) and j["attempts"]<=3 and integer(j["due"]),"JOB_ID_OR_ATTEMPT")
        keys.add(j["id"])
        allowed={"PENDING":(0,None),"SUCCEEDED":(None,"SUCCESS"),"RETRY_WAIT":(None,"TRANSIENT"),"BLOCKED":(None,None)}
        require(j["status"] in allowed,"JOB_STATUS")
        status=j["status"]; a=j["attempts"]; o=j["outcome"]
        require((status=="PENDING" and a==0 and o is None) or (status=="SUCCEEDED" and 1<=a<=3 and o=="SUCCESS") or (status=="RETRY_WAIT" and 1<=a<3 and o=="TRANSIENT") or (status=="BLOCKED" and 1<=a<=3 and o in ("TRANSIENT","PERMANENT")),"JOB_TRANSITION")
    prior=-1
    for r in cycles:
        require(exact(r,["slot","status","summary"]) and integer(r["slot"]) and s.slot(r["slot"])==r["slot"] and r["slot"]>prior and r["status"] in ("SUCCEEDED","BLOCKED","RETRY_WAIT") and isinstance(r["summary"],dict),"CYCLE_SCHEMA")
        prior=r["slot"]
    require(not any(r["status"]=="BLOCKED" for r in cycles[:-1]),"BLOCKED_HISTORY")
    return d
def export_bytes(directory):
    with q._tx(directory) as db:
        require(not db.execute("SELECT 1 FROM cycles WHERE status='RUNNING'").fetchone() and not db.execute("SELECT 1 FROM jobs WHERE status='RUNNING'").fetchone(),"IN_FLIGHT_NO_CHECKPOINT")
        require(not db.execute("SELECT 1 FROM jobs WHERE token IS NOT NULL").fetchone() and not db.execute("SELECT 1 FROM cycles WHERE token IS NOT NULL").fetchone(),"UNEXPECTED_TOKEN")
        data=dict(schema=SCHEMA,release="HOLD",production_recommendations="DISABLED",stopped=q._stopped(db),
            jobs=[dict(r) for r in db.execute("SELECT id,status,attempts,due,outcome FROM jobs ORDER BY id")],
            cycles=[dict(slot=r["slot"],status=r["status"],summary=json.loads(r["summary"])) for r in db.execute("SELECT slot,status,summary FROM cycles ORDER BY slot")])
        raw=canonical(validate(data))
        require(len(raw)<=MAX_BYTES,"CHECKPOINT_TOO_LARGE")
        return raw
def restore(directory,raw,expected_sha):
    require(isinstance(raw,bytes) and len(raw)<=MAX_BYTES and isinstance(expected_sha,str) and re.fullmatch(r"[0-9a-f]{64}",expected_sha) and hashlib.sha256(raw).hexdigest()==expected_sha,"CHECKPOINT_DIGEST_MISMATCH")
    data=validate(json.loads(raw))
    require(canonical(data)==raw,"NONCANONICAL_CHECKPOINT")
    s.init(directory) # Never overwrite existing state; no blank-state fallback.
    try:
        with q._tx(directory) as db:
            db.execute("UPDATE control SET stopped=? WHERE id=1",(int(data["stopped"]),))
            for j in data["jobs"]:
                db.execute("INSERT INTO jobs VALUES(?,?,?,?,NULL,?)",(j["id"],j["status"],j["attempts"],j["due"],j["outcome"]))
            for r in data["cycles"]:
                db.execute("INSERT INTO cycles VALUES(?,?,NULL,?)",(r["slot"],r["status"],json.dumps(r["summary"],sort_keys=True)))
        require(export_bytes(directory)==raw,"RESTORE_ROUNDTRIP_MISMATCH")
    except Exception:
        q.stop(directory)
        raise
    return dict(**FLAGS,restored=True,checkpointSha256=expected_sha,cycleCount=len(data["cycles"]),jobCount=len(data["jobs"]),anchorAuthenticated=False)
def health(directory,now=None):
    st=s.status(directory); rows=st["cycles"]
    level="NO_CYCLE"
    if st["stopped"] or any(r["status"] in ("RUNNING","BLOCKED") for r in rows):
        level="BLOCKED"
    elif rows:
        level="RETRY_WAIT" if rows[-1]["status"]=="RETRY_WAIT" else "RESEARCH_ONLY"
        if now is not None and s.slot(now)-rows[-1]["slot"]>=2*s.PERIOD:
            level="STALE"
    return dict(**FLAGS,level=level,cycleCount=len(rows),stopped=st["stopped"],notificationDelivered=False,
        reviewStatus="BLOCKED_INDEPENDENT_REVIEW_REQUIRED",storageStatus="CHECKPOINT_ONLY_NOT_PERMANENT")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["export","restore","health"])
    p.add_argument("directory",type=Path)
    p.add_argument("checkpoint",type=Path,nargs="?")
    p.add_argument("expected_sha",nargs="?")
    a=p.parse_args()
    try:
        if a.command=="export":
            require(a.checkpoint is not None and a.expected_sha is None,"ARGS")
            raw=export_bytes(a.directory)
            path=a.checkpoint.absolute()
            require(q.ROOT not in path.parents and path==path.resolve(),"CHECKPOINT_OUTSIDE_REPO")
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,"wb") as f:
                f.write(raw);f.flush();os.fsync(f.fileno())
            out=dict(**FLAGS,checkpointSha256=hashlib.sha256(raw).hexdigest(),size=len(raw))
        elif a.command=="restore":
            require(a.checkpoint is not None and a.expected_sha is not None and a.checkpoint.is_file() and not a.checkpoint.is_symlink() and a.checkpoint.stat().st_size<=MAX_BYTES,"ARGS")
            out=restore(a.directory,a.checkpoint.read_bytes(),a.expected_sha)
        else:
            require(a.checkpoint is None and a.expected_sha is None,"ARGS")
            out=health(a.directory,int(time.time()))
        print(json.dumps(out,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps(dict(**FLAGS,status="BLOCKED",reason=type(exc).__name__)))
        return 1
if __name__=="__main__": raise SystemExit(main())
