"""V24 opt-in, bounded BL1 shadow runner. No production or external scheduler.
The DB and lock must live on an owner-controlled persistent Linux filesystem.
All observed clocks remain local and unauthenticated.
"""
import argparse
import fcntl
import io
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from ops.v6_forward_bundle import pack,SCOPES,WEIGHTS,decode,digest,utc
from ops.v6_forward_comparison import seal
from ops.v6_forward_archive_audit import audit,FILES
from ops.v20_signed_receipts import sha,bounded
from ops.v22_forward_ledger import open_ledger,register,report,read
from ops.v23_forward_cycle import cycle
from ops.v21_raw_results import capture

INTERVALS={"forecast":timedelta(hours=6),"settlement":timedelta(hours=1)}
def clock():return datetime.now(timezone.utc)
def enc(obj):return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def init(db):
    db.executescript("""CREATE TABLE IF NOT EXISTS v24_attempts(
        kind TEXT NOT NULL, started_utc TEXT NOT NULL, PRIMARY KEY(kind,started_utc));
        CREATE TABLE IF NOT EXISTS v24_outcomes(
        kind TEXT NOT NULL, started_utc TEXT NOT NULL, finished_utc TEXT NOT NULL,
        state TEXT NOT NULL, PRIMARY KEY(kind,started_utc),
        FOREIGN KEY(kind,started_utc) REFERENCES v24_attempts(kind,started_utc));
        """)
def reserve(db,kind,now):
    db.execute("BEGIN IMMEDIATE")
    try:
        row=db.execute("SELECT started_utc FROM v24_attempts WHERE kind=? ORDER BY started_utc DESC LIMIT 1",(kind,)).fetchone()
        if row:
            elapsed=now-utc(row[0])
            if elapsed<timedelta(0):raise ValueError("RUNNER_CLOCK_REVERSED")
            if elapsed<INTERVALS[kind]:
                db.commit();return None
        stamp=now.isoformat()
        db.execute("INSERT INTO v24_attempts VALUES(?,?)",(kind,stamp))
        db.commit();return stamp
    except BaseException:
        db.rollback();raise
def complete(db,kind,started,state,now):
    if now<utc(started):raise ValueError("RUNNER_CLOCK_REVERSED")
    db.execute("INSERT INTO v24_outcomes VALUES(?,?,?,?)",(kind,started,now.isoformat(),state))
def excluded_scope(k,now):
    return {"league":SCOPES[k],"provider_league_shortcut":k,"provider":"OpenLigaDB",
        "schema":"v5-native-forward-shadow-v1","production_recommendations":"DISABLED",
        "verified_forward_sample_credit":0,"automatic_promotion":False,"weights":WEIGHTS,
        "generated_utc":now.isoformat(),"status":"HOLD","predictions":[],"predictions_count":0,
        "scheduled_in_window":None,"reason":"NOT_REQUESTED_BL1_ONLY",
        **dict.fromkeys(("source_independent","result_authentication","external_capture_witness_verified",
                         "feature_availability_independently_verified","market_odds_available"),False)}
def freeze(native_raw,cal_raw,cal_digest,*,now_fn=clock):
    bounded(native_raw,2_000_000);bounded(cal_raw,3_000_000)
    if sha(cal_raw)!=digest(cal_digest):raise ValueError("CALIBRATION_DIGEST")
    n=decode(native_raw);cal=decode(cal_raw);now=utc(now_fn().isoformat())
    if n.get("reason") and not n.get("predictions"):raise ValueError("NATIVE_SOURCE_UNAVAILABLE")
    bundle=pack({"bl1":n,**{k:excluded_scope(k,now) for k in ("bl2","bl3")}},now)
    bundle["input_artifact_sha256"]={"bl1":sha(native_raw)}
    b=enc(bundle)
    record=seal(bundle,cal,now);record["input_sha256"]=[sha(b),sha(cal_raw)]
    stream=io.BytesIO()
    with ZipFile(stream,"w",compression=ZIP_DEFLATED) as z:
        for name,data in zip(FILES,(enc(record),b,cal_raw)):z.writestr(name,data)
    raw=stream.getvalue();created=utc(now_fn().isoformat())
    audit(raw,sha(raw),created)
    return raw,created,len(record["rows"])
def produce():
    # Existing native BL1 producer makes two bounded public requests.
    with tempfile.TemporaryDirectory() as d:
        output=Path(d)/"native.json"
        subprocess.run([sys.executable,"-m","ops.v5_native_bundesliga_forward","--league","bl1",
            "--joint","ops/v5_joint_poisson.py","--elo","ops/v5_dynamic_elo.py",
            "--ml","ops/v5_ml_benchmark.py","--ensemble","ops/v5_ensemble_competition.py",
            "--output",str(output)],check=True,capture_output=True,timeout=180)
        return read(output,2_000_000)
def health(db,now):
    last={}
    for kind,interval in INTERVALS.items():
        row=db.execute("""SELECT a.started_utc,o.finished_utc,o.state FROM v24_attempts a
            LEFT JOIN v24_outcomes o USING(kind,started_utc)
            WHERE a.kind=? ORDER BY a.started_utc DESC LIMIT 1""",(kind,)).fetchone()
        last[kind]=None if row is None else {"started_utc":row[0],"finished_utc":row[1],
            "state":row[2] or "INCOMPLETE_ATTEMPT",
            "overdue":now-utc(row[0])>interval*2}
    return last
def tick(db,cal_raw,cal_digest,*,producer=produce,capture_fn=capture,now_fn=clock):
    # Verify configuration before any network budget is consumed.
    bounded(cal_raw,3_000_000)
    if sha(cal_raw)!=digest(cal_digest):raise ValueError("CALIBRATION_DIGEST")
    cal=decode(cal_raw)
    if (cal.get("schema")!="v6-1-league-calibration-research-v1" or cal.get("status")!="HOLD"
        or cal.get("production_recommendations")!="DISABLED" or cal.get("automatic_promotion") is not False
        or cal.get("prospective_validation") is not False or cal.get("cutoff")!="2026-01-01"):
        raise ValueError("CALIBRATION_CONTRACT")
    from ops.v6_calibration_challenger import calibrate
    calibrate([.4,.3,.3],*cal["per_league"]["de.1"]["params"])
    init(db);out={}
    for kind in INTERVALS:
        started=reserve(db,kind,utc(now_fn().isoformat()))
        if started is None:out[kind]={"state":"THROTTLED"};continue
        if kind=="forecast":
            try:
                raw,created,n=freeze(producer(),cal_raw,cal_digest,now_fn=now_fn)
                entry=register(db,raw,sha(raw),created.isoformat(),as_of=utc(now_fn().isoformat()).isoformat())
                out[kind]={"state":"SEALED" if n else "NO_ELIGIBLE_FIXTURES","sealed":n,"registration":entry}
            except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError,subprocess.SubprocessError) as exc:
                out[kind]={"state":"HOLD_FORECAST_FAILED","error_class":type(exc).__name__}
        else:
            result=cycle(db,capture_fn=capture_fn,clock=now_fn)
            out[kind]={"state":"HOLD_PENDING_REVIEW" if result["reasons"] else "CHECKED","cycle":result}
        complete(db,kind,started,out[kind]["state"],utc(now_fn().isoformat()))
    return {"schema":"v24-shadow-runner-v1","tasks":out,"health":health(db,utc(now_fn().isoformat())),
        "ledger":report(db),"forecast_interval_hours":6,"settlement_interval_hours":1,
        "maximum_public_requests_per_tick":4,"verified_forward_sample_credit":0,
        "automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--state-dir",required=True)
    p.add_argument("--calibration",required=True);p.add_argument("--calibration-sha256",required=True)
    a=p.parse_args();root=Path(a.state_dir)
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode&0o077:raise ValueError("PRIVATE_STATE_DIRECTORY_REQUIRED")
    fd=os.open(root/"runner.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"rb+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        db=open_ledger(root/"ledger.sqlite")
        try:out=tick(db,read(a.calibration,3_000_000),a.calibration_sha256)
        finally:db.close()
        print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
