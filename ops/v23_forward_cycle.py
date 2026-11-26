"""V23 bounded restartable BL1 research settlement cycle, no production switch.
One public request per selected season, at most two per explicit invocation.
The owner must provide a durable database and scheduling; no background loop.
"""
import argparse
import hashlib
import json
import os
import sqlite3
from collections import defaultdict,Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
from ops.v22_forward_ledger import open_ledger,register,settle,report,read
from ops.v21_raw_results import capture,URLS
from ops.v5_native_bundesliga_forward import normalize
from ops.v6_forward_bundle import utc,decode
from ops.v20_signed_receipts import bounded,sha

MAX_SEASONS=2
MAX_DUE=100
MAX_AGE=900

def due_fixtures(db,now):
    # Query only never-settled fixtures. No second-source calls or regrading.
    rows=db.execute("""SELECT f.fixture_id,f.kickoff_utc FROM fixtures f
        WHERE NOT EXISTS(SELECT 1 FROM settlements s WHERE s.fixture_id=f.fixture_id)
        ORDER BY f.kickoff_utc,f.fixture_id""").fetchall()
    groups=defaultdict(list)
    for mid,stamp in rows:
        ko=utc(stamp)
        if ko+timedelta(hours=2)<=now:
            groups[ko.year-int(ko.month<7)].append(mid)
    return groups

def validate_capture(raw,meta,year,now):
    bounded(raw,3_000_000)
    if (type(meta) is not dict or meta.get("provider")!="openligadb" or
        meta.get("season")!=year or meta.get("source")!=URLS["openligadb"]+str(year) or
        meta.get("sha256")!=sha(raw) or meta.get("bytes")!=len(raw) or
        meta.get("source_authenticated") is not False):
        raise ValueError("CAPTURE_RECEIPT")
    obs=utc(meta["captured_utc"])
    if not 0<=(now-obs).total_seconds()<=MAX_AGE:raise ValueError("CAPTURE_CLOCK")
    doc=decode(raw)
    normalize(doc,year,obs,shortcut="bl1")
    return obs,{str(x["matchID"]):x for x in doc}

def cycle(db,*,capture_fn=capture,clock=lambda:datetime.now(timezone.utc)):
    now=utc(clock().isoformat())
    groups=due_fixtures(db,now)
    count=sum(map(len,groups.values()))
    attempted=0;settled=0;reasons=Counter();sources=[];remaining=MAX_DUE
    # All provider responses are validated before individual settlement.
    for year in sorted(groups)[:MAX_SEASONS]:
        if not remaining:break
        ids=groups[year][:remaining];remaining-=len(ids);attempted+=len(ids)
        try:
            raw,meta=capture_fn("openligadb",year)
            end=utc(clock().isoformat())
            if end<now:raise ValueError("CYCLE_CLOCK_REVERSED")
            obs,lookup=validate_capture(raw,meta,year,end)
            sources.append({"season":year,"status":"OBSERVED_SINGLE_SOURCE","receipt":meta})
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError) as exc:
            reasons["SOURCE_UNAVAILABLE_OR_INVALID"]+=len(ids)
            sources.append({"season":year,"status":"HOLD","error_class":type(exc).__name__})
            continue
        for mid in ids:
            row=lookup.get(mid)
            if row is None:
                reasons["MISSING_EVENT"]+=1;continue
            if row["matchIsFinished"] is not True:
                reasons["NOT_FINISHED"]+=1;continue
            try:
                result=settle(db,mid,raw,obs.isoformat(),as_of=end.isoformat())
                if result["duplicate"]:reasons["ALREADY_SETTLED"]+=1
                else:settled+=1
            except (ValueError,TypeError,KeyError,AttributeError,OverflowError) as exc:
                reasons["FIXTURE_REVIEW_REQUIRED"]+=1
    summary=report(db)
    return {"schema":"v23-forward-cycle-research-v1","started_utc":now.isoformat(),
        "due_at_start":count,"attempted":attempted,"newly_settled":settled,
        "deferred_by_budget":count-attempted,"reasons":dict(reasons),"sources":sources,
        "ledger":summary,"request_limit_per_cycle":MAX_SEASONS,"automatic_retry":False,
        "second_provider_called":False,"verified_forward_sample_credit":0,
        "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}

def backup(db,path):
    """Consistent SQLite snapshot. Exclusive destination; no overwrite."""
    p=Path(path)
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    try:
        target=sqlite3.connect(p)
        try:
            db.backup(target)
            if target.execute("PRAGMA integrity_check").fetchall()!=[("ok",)]:raise ValueError("BACKUP_INTEGRITY")
            if target.execute("PRAGMA foreign_key_check").fetchall():raise ValueError("BACKUP_FOREIGN_KEYS")
            summary=report(target)
        finally:target.close()
        h=hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
        return {"sha256":h.hexdigest(),"bytes":p.stat().st_size,"unique_fixture_count":summary["unique_fixture_count"],
                "local_backup_only":True,"verified_forward_sample_credit":0}
    except BaseException:
        p.unlink(missing_ok=True);raise

def main():
    p=argparse.ArgumentParser();p.add_argument("--db",required=True)
    p.add_argument("--archive");p.add_argument("--archive-sha256");p.add_argument("--archive-created-utc")
    p.add_argument("--backup");a=p.parse_args()
    supplied=(a.archive,a.archive_sha256,a.archive_created_utc)
    if any(x is not None for x in supplied) and not all(x is not None for x in supplied):raise ValueError("ARCHIVE_ARGUMENTS")
    db=open_ledger(a.db)
    try:
        imported=register(db,read(a.archive),a.archive_sha256,a.archive_created_utc) if a.archive else None
        out=cycle(db);out["archive_import"]=imported
        if a.backup:out["backup"]=backup(db,a.backup)
        print(json.dumps(out,allow_nan=False))
    finally:db.close()
if __name__=="__main__":main()
