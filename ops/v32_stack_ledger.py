"""V32 durable same-cut research ledger (local, no external attestation).
Imports actual V27 archives; first admitted forecast frozen across invocations.
"""
import argparse,json,sqlite3
from datetime import datetime,timezone,timedelta
from pathlib import Path
from ops.v22_forward_ledger import open_ledger as open_local,read
from ops.v27_stack_archive import audit,MODELS,sha
from ops.v6_forward_bundle import utc,native
from ops.v21_raw_results import verify_result
from ops.v23_forward_cycle import validate_capture
from ops.v5_ensemble_competition import metrics
from ops.v20_signed_receipts import bounded

LIMIT=3_000_000

def research_only():
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "verified_forward_sample_credit":0,"automatic_promotion":False}
def open_ledger(path):
    db=open_local(path)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS v32_archives(digest TEXT PRIMARY KEY, raw BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS v32_fixtures(mid TEXT PRIMARY KEY, digest TEXT NOT NULL REFERENCES v32_archives(digest),h TEXT NOT NULL,a TEXT NOT NULL,ko TEXT NOT NULL,UNIQUE(h,a,ko));
    CREATE TABLE IF NOT EXISTS v32_results(mid TEXT PRIMARY KEY REFERENCES v32_fixtures(mid),raw BLOB NOT NULL,observed TEXT NOT NULL,raw_digest TEXT NOT NULL);
    """)
    for table in ("v32_archives","v32_fixtures","v32_results"):
        for op in ("UPDATE","DELETE"):
            db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{op.lower()} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'IMMUTABLE_RESEARCH_ROW'); END")
    return db
def register(db,raw,expected,now):
    record=audit(raw,expected);sealed=utc(record["sealed_utc"])
    if sealed>now:raise ValueError("FUTURE_ARCHIVE")
    inserted=duplicates=0
    db.execute("BEGIN IMMEDIATE")
    try:
        old=db.execute("SELECT raw FROM v32_archives WHERE digest=?",(expected,)).fetchone()
        if old and old[0]!=raw:raise ValueError("ARCHIVE_CONFLICT")
        if not old:db.execute("INSERT INTO v32_archives VALUES(?,?)",(expected,raw))
        for r in record["rows"]:
            mid,h,a,ko=(r[k] for k in ("fixture_id","home_id","away_id","kickoff_utc"))
            saved=db.execute("SELECT f.h,f.a,f.ko,z.raw,z.digest FROM v32_fixtures f JOIN v32_archives z USING(digest) WHERE f.mid=?",(mid,)).fetchone()
            if saved:
                if saved[:3]!=(h,a,ko):raise ValueError("FIXTURE_IDENTITY_CONFLICT")
                if sealed<utc(audit(saved[3],saved[4])["sealed_utc"]):raise ValueError("OUT_OF_ORDER_ARCHIVE")
                duplicates+=1;continue
            if db.execute("SELECT mid FROM v32_fixtures WHERE h=? AND a=? AND ko=?",(h,a,ko)).fetchone():raise ValueError("FIXTURE_ALIAS_CONFLICT")
            db.execute("INSERT INTO v32_fixtures VALUES(?,?,?,?,?)",(mid,expected,h,a,ko));inserted+=1
        db.commit()
    except BaseException:db.rollback();raise
    return {**research_only(),"inserted":inserted,"duplicates":duplicates}
def fixture(db,mid):
    q=db.execute("SELECT f.h,f.a,f.ko,z.raw,z.digest FROM v32_fixtures f JOIN v32_archives z USING(digest) WHERE f.mid=?",(native(mid),)).fetchone()
    if q is None:raise ValueError("UNKNOWN_FIXTURE")
    h,a,ko,raw,d=q;record=audit(raw,d)
    rows=[r for r in record["rows"] if r["fixture_id"]==mid]
    if len(rows)!=1 or (rows[0]["home_id"],rows[0]["away_id"],rows[0]["kickoff_utc"])!=(h,a,ko):raise ValueError("LEDGER_BINDING")
    return rows[0],utc(record["sealed_utc"])
def case(db,mid,raw,observed,expected):
    if sha(raw)!=expected:raise ValueError("RESULT_DIGEST")
    r,sealed=fixture(db,mid)
    if observed<=sealed:raise ValueError("RESULT_CLOCK")
    q=verify_result(raw,"openligadb",fixture_id=mid,home_id=r["home_id"],away_id=r["away_id"],kickoff_utc=r["kickoff_utc"],observed_utc=observed.isoformat())
    h,a=q["score"];return {**r,"score":[h,a],"date":utc(r["kickoff_utc"]).date().isoformat(),"y":0 if h>a else 1 if h==a else 2}
def settle(db,mid,raw,observed,now):
    bounded(raw,LIMIT)
    if observed>now:raise ValueError("FUTURE_RESULT")
    d=sha(raw);db.execute("BEGIN IMMEDIATE")
    try:
        a=case(db,mid,raw,observed,d)
        old=db.execute("SELECT raw,observed,raw_digest FROM v32_results WHERE mid=?",(mid,)).fetchone()
        if old:
            b=case(db,mid,old[0],utc(old[1]),old[2])
            if a["score"]!=b["score"]:raise ValueError("RESULT_CONFLICT")
        else:db.execute("INSERT INTO v32_results VALUES(?,?,?,?)",(mid,raw,observed.isoformat(),d))
        db.commit()
    except BaseException:db.rollback();raise
    return {**research_only(),"duplicate":old is not None,"score":a["score"]}
def report(db):
    db.execute("BEGIN")
    try:
        arcs=db.execute("SELECT digest,raw FROM v32_archives").fetchall()
        for d,raw in arcs:audit(raw,d)
        ids=[q[0] for q in db.execute("SELECT mid FROM v32_fixtures ORDER BY mid")]
        cases=[]
        for mid in ids:
            fixture(db,mid)
            q=db.execute("SELECT raw,observed,raw_digest FROM v32_results WHERE mid=?",(mid,)).fetchone()
            if q:cases.append(case(db,mid,q[0],utc(q[1]),q[2]))
        db.commit()
    except BaseException:db.rollback();raise
    from ops.v9_league_weights import ci
    return {"schema":"v32-same-cut-ledger-research-v1","archive_count":len(arcs),"unique_fixture_count":len(ids),"settled_count":len(cases),"pending_count":len(ids)-len(cases),
        "metrics":{k:metrics(cases,lambda r:r[k]) for k in MODELS},
        "paired_week_ci_v5_minus_stack":ci([{**r,"hybrid":r["v5"],"candidate":r["v10_1"]} for r in cases]),
        "single_source_research_only":True,"first_admitted_forecast_only":True,"verified_forward_sample_credit":0,
        "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--db",required=True);sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("register");a.add_argument("--archive",required=True);a.add_argument("--sha256",required=True)
    s=sub.add_parser("settle");s.add_argument("--fixture-id",required=True);s.add_argument("--results",required=True);s.add_argument("--observed-utc",required=True)
    sub.add_parser("report");a=p.parse_args();db=open_ledger(a.db);now=datetime.now(timezone.utc)
    try:
        if a.cmd=="register":out=register(db,read(a.archive),a.sha256,now)
        elif a.cmd=="settle":out=settle(db,a.fixture_id,read(a.results),utc(a.observed_utc),now)
        else:out=report(db)
        print(json.dumps(out,allow_nan=False))
    finally:db.close()
if __name__=="__main__":main()
