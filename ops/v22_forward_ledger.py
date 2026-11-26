"""V22 persistent local research ledger; never independent evidence.
One admitted forecast per BL1 native event. SQLite transactions prevent
partial batches. An owner with database access can still rewrite the file.
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime,timezone
from pathlib import Path
from ops.v6_forward_archive_audit import audit,LIMIT
from ops.v6_forward_bundle import utc,native
from ops.v20_signed_receipts import sha,bounded
from ops.v21_raw_results import verify_result,compare
from ops.v5_ensemble_competition import metrics,vec

SCHEMA="""
CREATE TABLE IF NOT EXISTS archives(
    digest TEXT PRIMARY KEY, created_utc TEXT NOT NULL, raw BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS fixtures(
    fixture_id TEXT PRIMARY KEY, archive_digest TEXT NOT NULL REFERENCES archives(digest),
    home_id TEXT NOT NULL, away_id TEXT NOT NULL, kickoff_utc TEXT NOT NULL,
    UNIQUE(home_id,away_id,kickoff_utc));
CREATE TABLE IF NOT EXISTS settlements(
    fixture_id TEXT NOT NULL REFERENCES fixtures(fixture_id),
    kind TEXT NOT NULL CHECK(kind IN ('single','dual')),
    open_raw BLOB NOT NULL, open_observed_utc TEXT NOT NULL,
    fd_raw BLOB, fd_observed_utc TEXT, mapping_raw BLOB, mapping_digest TEXT,
    PRIMARY KEY(fixture_id,kind));
"""
TABLES=("archives","fixtures","settlements")
def open_ledger(path):
    p=Path(path)
    if not p.exists():
        fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    if p.is_symlink() or not p.is_file():raise ValueError("LEDGER_PATH")
    db=sqlite3.connect(p,timeout=10,isolation_level=None)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=10000")
    db.executescript(SCHEMA)
    for table in TABLES:
        for op in ("UPDATE","DELETE"):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RESEARCH_ROW'); END")
    return db

def _now(as_of):
    return utc(as_of) if as_of is not None else datetime.now(timezone.utc)

def register(db,raw,expected_sha256,created_utc,*,as_of=None):
    created=utc(created_utc)
    if created>_now(as_of):raise ValueError("FUTURE_ARCHIVE")
    record,_=audit(bounded(raw,LIMIT),expected_sha256,created)
    inserted=duplicates=0
    db.execute("BEGIN IMMEDIATE")
    try:
        old=db.execute("SELECT created_utc,raw FROM archives WHERE digest=?",(expected_sha256,)).fetchone()
        if old is not None and (utc(old[0])!=created or old[1]!=raw):raise ValueError("ARCHIVE_REPLAY_CONFLICT")
        if old is None:db.execute("INSERT INTO archives VALUES(?,?,?)",(expected_sha256,created.isoformat(),raw))
        for r in record["rows"]:
            mid=native(r["provider_event_id"]);h=native(r["home_native_id"]);a=native(r["away_native_id"]);ko=utc(r["kickoff_utc"]).isoformat()
            saved=db.execute("SELECT f.home_id,f.away_id,f.kickoff_utc,a.created_utc FROM fixtures f JOIN archives a ON a.digest=f.archive_digest WHERE f.fixture_id=?",(mid,)).fetchone()
            if saved:
                if saved[:3]!=(h,a,ko):raise ValueError("FIXTURE_IDENTITY_CONFLICT")
                if created<utc(saved[3]):raise ValueError("OUT_OF_ORDER_ARCHIVE")
                duplicates+=1;continue
            alias=db.execute("SELECT fixture_id FROM fixtures WHERE home_id=? AND away_id=? AND kickoff_utc=?",(h,a,ko)).fetchone()
            if alias:raise ValueError("FIXTURE_ALIAS_CONFLICT")
            db.execute("INSERT INTO fixtures VALUES(?,?,?,?,?)",(mid,expected_sha256,h,a,ko));inserted+=1
        db.commit()
    except BaseException:
        db.rollback();raise
    return {"inserted":inserted,"duplicates":duplicates,"archive_sha256":expected_sha256,
            "status":"HOLD","production_recommendations":"DISABLED","verified_forward_sample_credit":0}

def _fixture(db,mid):
    row=db.execute("SELECT f.home_id,f.away_id,f.kickoff_utc,a.digest,a.created_utc,a.raw FROM fixtures f JOIN archives a ON a.digest=f.archive_digest WHERE fixture_id=?",(native(mid),)).fetchone()
    if row is None:raise ValueError("UNKNOWN_FIXTURE")
    h,a,ko,digest,created,raw=row
    record,_=audit(raw,digest,utc(created))
    rows=[r for r in record["rows"] if r["provider_event_id"]==mid]
    if len(rows)!=1:raise ValueError("LEDGER_ARCHIVE_BINDING")
    r=rows[0]
    if (r["home_native_id"],r["away_native_id"],utc(r["kickoff_utc"]).isoformat())!=(h,a,ko):
        raise ValueError("LEDGER_IDENTITY_BINDING")
    return r,{"fixture_id":mid,"home_id":h,"away_id":a,"kickoff_utc":ko}

def _result(db,mid,record):
    kind,ol,ot,fd,ft,mapping,md=record
    r,common=_fixture(db,mid)
    if kind=="single":
        if any(x is not None for x in (fd,ft,mapping,md)):raise ValueError("SINGLE_RESULT_FIELDS")
        score=verify_result(ol,"openligadb",observed_utc=ot,**common)["score"]
    elif kind=="dual":
        score=compare(ol,fd,open_observed_utc=ot,fd_observed_utc=ft,
                      mapping_raw=mapping,mapping_sha256=md,**common)["score"]
    else:raise ValueError("RESULT_KIND")
    h,a=score
    return {"fixture_id":mid,"score":[h,a],"y":0 if h>a else 1 if h==a else 2,
            "baseline":vec(r["baseline"]),"candidate":vec(r["candidate"])}

def settle(db,mid,open_raw,open_observed_utc,*,fd_raw=None,fd_observed_utc=None,mapping_raw=None,mapping_sha256=None,as_of=None):
    mid=native(mid);now=_now(as_of);ot=utc(open_observed_utc)
    supplied=(fd_raw,fd_observed_utc,mapping_raw,mapping_sha256)
    if any(x is not None for x in supplied) and not all(x is not None for x in supplied):
        raise ValueError("INCOMPLETE_DUAL_RESULT")
    kind="dual" if fd_raw is not None else "single"
    ft=utc(fd_observed_utc) if kind=="dual" else None
    if ot>now or (ft is not None and ft>now):raise ValueError("FUTURE_RESULT")
    row=(kind,bounded(open_raw,LIMIT),ot.isoformat(),fd_raw,ft.isoformat() if ft else None,mapping_raw,mapping_sha256)
    db.execute("BEGIN IMMEDIATE")
    try:
        case=_result(db,mid,row)
        existing=db.execute("SELECT kind,open_raw,open_observed_utc,fd_raw,fd_observed_utc,mapping_raw,mapping_digest FROM settlements WHERE fixture_id=?",(mid,)).fetchall()
        duplicate=False
        for prior in existing:
            if _result(db,mid,prior)["score"]!=case["score"]:raise ValueError("SETTLEMENT_SCORE_CONFLICT")
            if prior[0]==kind:duplicate=True
        if not duplicate:db.execute("INSERT INTO settlements VALUES(?,?,?,?,?,?,?,?)",(mid,*row))
        db.commit()
    except BaseException:
        db.rollback();raise
    return {"fixture_id":mid,"kind":kind,"score":case["score"],"duplicate":duplicate,
            "status":"HOLD","production_recommendations":"DISABLED","verified_forward_sample_credit":0}

def report(db):
    # Re-read all stored archives and raw results, do not trust cached metrics.
    db.execute("BEGIN")
    try:
        archives=db.execute("SELECT digest,created_utc,raw FROM archives ORDER BY created_utc,digest").fetchall()
        for d,t,raw in archives:audit(raw,d,utc(t))
        ids=[r[0] for r in db.execute("SELECT fixture_id FROM fixtures ORDER BY fixture_id")]
        cases=[];dual=[]
        for mid in ids:
            _fixture(db,mid)
            rows=db.execute("SELECT kind,open_raw,open_observed_utc,fd_raw,fd_observed_utc,mapping_raw,mapping_digest FROM settlements WHERE fixture_id=?",(mid,)).fetchall()
            checked={r[0]:_result(db,mid,r) for r in rows}
            if "single" in checked and "dual" in checked and checked["single"]["score"]!=checked["dual"]["score"]:
                raise ValueError("SETTLEMENT_SCORE_CONFLICT")
            if checked:cases.append(checked.get("dual",checked.get("single")))
            if "dual" in checked:dual.append(checked["dual"])
        db.commit()
    except BaseException:
        db.rollback();raise
    def paired(a):return {k:metrics(a,lambda r:r[k]) for k in ("baseline","candidate")}
    return {"schema":"v22-local-forward-ledger-v1","archive_count":len(archives),"unique_fixture_count":len(ids),
            "settled_research_count":len(cases),"pending_count":len(ids)-len(cases),"dual_raw_research_count":len(dual),
            "paired_research_metrics":paired(cases),"dual_raw_paired_metrics":paired(dual),
            "first_admitted_forecast_only":True,"local_storage_not_external_attestation":True,
            "source_independence_verified":False,"verified_forward_sample_credit":0,
            "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}

def read(path,limit=LIMIT):
    p=Path(path)
    if not 0<p.stat().st_size<=limit:raise ValueError("FILE_SIZE")
    return bounded(p.read_bytes(),limit)

def main():
    p=argparse.ArgumentParser();p.add_argument("--db",required=True);sub=p.add_subparsers(dest="command",required=True)
    add=sub.add_parser("register");add.add_argument("--archive",required=True);add.add_argument("--sha256",required=True);add.add_argument("--created-utc",required=True)
    s=sub.add_parser("settle")
    for k in ("fixture-id","open-raw","open-observed-utc"):s.add_argument("--"+k,required=True)
    for k in ("fd-raw","fd-observed-utc","mapping","mapping-sha256"):s.add_argument("--"+k)
    sub.add_parser("report");a=p.parse_args();db=open_ledger(a.db)
    try:
        if a.command=="register":out=register(db,read(a.archive),a.sha256,a.created_utc)
        elif a.command=="settle":out=settle(db,a.fixture_id,read(a.open_raw),a.open_observed_utc,
            fd_raw=read(a.fd_raw) if a.fd_raw else None,fd_observed_utc=a.fd_observed_utc,
            mapping_raw=read(a.mapping,100000) if a.mapping else None,mapping_sha256=a.mapping_sha256)
        else:out=report(db)
        print(json.dumps(out,allow_nan=False))
    finally:db.close()
if __name__=="__main__":main()
