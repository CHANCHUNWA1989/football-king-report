"""V3.2 continuity qualification: trusted external anchor required; no production authority."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import deployment_checkpoint as c
import research_scheduler as s

REPO="CHANCHUNWA1989/football-king-report"
GRACE=47*60
FLAGS=dict(**c.FLAGS,notificationDelivered=False)
def require(ok,reason):
    if not ok: raise ValueError(reason)
def digest(raw):
    return hashlib.sha256(raw).hexdigest()
def decode(raw):
    require(isinstance(raw,bytes) and len(raw)<=c.MAX_BYTES,"CHECKPOINT_LIMIT")
    d=c.validate(json.loads(raw))
    require(c.canonical(d)==raw,"NONCANONICAL_CHECKPOINT")
    return d
def anchor(raw,run_id,artifact_id,head):
    d=decode(raw)
    require(type(run_id) is int and run_id>0 and type(artifact_id) is int and artifact_id>0 and isinstance(head,str) and re.fullmatch(r"[0-9a-f]{40}",head),"ANCHOR_IDENTITY")
    require(bool(d["cycles"]),"EMPTY_PREDECESSOR")
    return dict(repository=REPO,runId=run_id,artifactId=artifact_id,headSha=head,checkpointSha256=digest(raw),lastSlot=d["cycles"][-1]["slot"],cycleCount=len(d["cycles"]))
def verify(raw,expected,observed):
    require(isinstance(expected,dict) and set(expected)=={"repository","runId","artifactId","headSha","checkpointSha256","lastSlot","cycleCount"},"ANCHOR_SCHEMA")
    require(isinstance(observed,dict) and set(observed)=={"repository","runId","artifactId","headSha","conclusion","expired"},"OBSERVED_SCHEMA")
    require(observed["conclusion"]=="success" and observed["expired"] is False and observed["repository"]==REPO and expected["repository"]==REPO,"PREDECESSOR_UNAVAILABLE")
    require(all(observed[k]==expected[k] and type(observed[k]) is type(expected[k]) for k in ("runId","artifactId","headSha")),"PREDECESSOR_IDENTITY")
    actual=anchor(raw,observed["runId"],observed["artifactId"],observed["headSha"])
    require(actual==expected and all(type(actual[k]) is type(expected[k]) for k in actual),"PREDECESSOR_DIGEST_OR_VERSION")
    return decode(raw)
def successor(old,new):
    a,b=decode(old),decode(new)
    require(len(b["cycles"])>len(a["cycles"]) and b["cycles"][:len(a["cycles"])]==a["cycles"],"CYCLE_ROLLBACK_OR_REWRITE")
    require(not a["stopped"] and not any(r["status"]=="BLOCKED" for r in a["cycles"]),"PREDECESSOR_STOPPED")
    before={j["id"]:j for j in a["jobs"]};after={j["id"]:j for j in b["jobs"]}
    require(set(before)<=set(after),"JOB_REMOVED")
    for k,j in before.items():
        n=after[k]
        require(n["attempts"]>=j["attempts"],"ATTEMPT_ROLLBACK")
        if j["status"] in ("SUCCEEDED","BLOCKED"):
            require(j==n,"TERMINAL_JOB_REWRITE")
        elif j["status"]=="RETRY_WAIT":
            require(n["status"]!="PENDING" and (n["attempts"]>j["attempts"] or n==j),"RETRY_ROLLBACK")
        elif j["status"]=="PENDING" and n["status"]=="PENDING":
            require(n==j,"PENDING_REWRITE")
    return dict(**FLAGS,predecessorSha256=digest(old),successorSha256=digest(new),addedCycles=len(b["cycles"])-len(a["cycles"]),anchorAuthenticated=False)
def monitor(d,now):
    d=c.validate(d)
    require(type(now) is int and now>=0,"CLOCK_INVALID")
    current=s.slot(now)
    due=current if now-current>=GRACE else current-s.PERIOD
    rows=d["cycles"]
    if not rows:
        return dict(**FLAGS,level="NO_CYCLE",missedSlots=None,lateCurrent=False,observationStart=None)
    last=rows[-1]["slot"];first=rows[0]["slot"]
    require(last<=current,"CLOCK_ROLLBACK")
    completed={r["slot"] for r in rows if r["status"]=="SUCCEEDED"}
    expected=max(0,(due-first)//s.PERIOD+1)
    missed=expected-sum(first<=v<=due for v in completed)
    late=due>=first and due not in completed
    level="BLOCKED" if d["stopped"] or any(r["status"]=="BLOCKED" for r in rows) else "MISSED_SCHEDULE" if missed else "RETRY_WAIT" if rows[-1]["status"]=="RETRY_WAIT" else "RESEARCH_ONLY"
    return dict(**FLAGS,level=level,missedSlots=missed,lateCurrent=late,observationStart=first,lastSlot=last,latestDueSlot=due,graceSeconds=GRACE)
def read(p):
    require(p.is_file() and not p.is_symlink() and p.stat().st_size<=c.MAX_BYTES,"UNSAFE_INPUT")
    return p.read_bytes()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["restore","monitor","successor"])
    p.add_argument("paths",type=Path,nargs="+")
    a=p.parse_args()
    try:
        if a.command=="restore" and len(a.paths)==4:
            raw,expected,observed,dest=a.paths
            raw=read(raw);expected=json.loads(read(expected));observed=json.loads(read(observed))
            d=verify(raw,expected,observed)
            out=dict(c.restore(dest,raw,expected["checkpointSha256"]),predecessorRunId=expected["runId"],predecessorArtifactId=expected["artifactId"],lastSlot=d["cycles"][-1]["slot"],anchorAuthenticated=False)
        elif a.command=="monitor" and len(a.paths)==1:
            out=monitor(decode(read(a.paths[0])),int(time.time()))
        elif a.command=="successor" and len(a.paths)==2:
            out=successor(read(a.paths[0]),read(a.paths[1]))
        else: raise ValueError("ARGS")
        print(json.dumps(out,sort_keys=True));return 0
    except Exception as e:
        print(json.dumps(dict(**FLAGS,status="BLOCKED",reason=str(e) if isinstance(e,ValueError) else type(e).__name__)))
        return 1
if __name__=="__main__": raise SystemExit(main())
