"""V34 explicit invocation of the V10.1 BL1 shadow runner.
Persist a private V32 ledger on one host; no external scheduler or production.
"""
import argparse,fcntl,json,math,os,re
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path
from ops import v25_native_stack as stack,v27_stack_archive as archive,v32_stack_ledger as ledger
from ops import v9_stacking_research as s,v9_league_weights as w,v8_multiseason as v
from ops.v24_shadow_runner import init,reserve,complete,health,INTERVALS
from ops.v23_forward_cycle import validate_capture
from ops.v21_raw_results import capture
from ops.v6_forward_bundle import utc,decode,digest
from ops.v20_signed_receipts import bounded,sha
from ops.v5_ensemble_competition import vec

MAX_DUE=100
ERRORS=(OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError)
def clock():return datetime.now(timezone.utc)
def preflight(raw,expected):
    bounded(raw,3_000_000)
    if sha(raw)!=digest(expected):raise ValueError("EXPORT_DIGEST")
    d=decode(raw);archive.safe(d)
    if d["schema"]!="v25-portable-stack-export-v1":raise ValueError("EXPORT_SCHEMA")
    for k,limit in (("portable",1e-10),("native_feature",1e-7),("prefix",1e-7)):
        n=d[k+"_parity_n"];err=d[k+"_max_abs_error"]
        if type(n) is not int or n<20 or type(err) not in (float,int) or not math.isfinite(err) or not 0<=err<=limit:raise ValueError("EXPORT_PARITY")
    m=d["model"]
    if m["historical_source_commit"]!=v.PIN or tuple(m["training_seasons"])!=s.TRAIN or m["calibration_season"]!=s.CAL or m["status"]!="HOLD" or m["production_recommendations"]!="DISABLED" or m["verified_forward_sample_credit"]!=0:raise ValueError("EXPORT_MODEL")
    q={k:[.4,.3,.3] for k in s.EXPERTS}
    s.combine(stack.portable(m,{"experts":q}),[.4,.3,.3],m["temperature"],m["stack_weight"])
    tail=d["de1_prior_tail"]
    if len(tail)!=w.WINDOW:raise ValueError("EXPORT_TAIL")
    dates=[]
    for a in tail:
        t=datetime.fromisoformat(a["date"]).date()
        if t.isoformat()!=a["date"] or not "2022-07-01"<=a["date"]<"2026-07-01" or type(a["y"]) is not int or a["y"] not in (0,1,2) or set(a["experts"])!=set(s.EXPERTS):raise ValueError("EXPORT_TAIL")
        dates.append(t)
        for x in a["experts"].values():vec(x)
    if dates!=sorted(dates):raise ValueError("EXPORT_TAIL_ORDER")
    return d
def produce(exp,export_raw,*,capture_fn,clock_fn):
    captures=[]
    out=stack.live(exp,capture_fn=capture_fn,clock=clock_fn,capture_sink=lambda a,b:captures.extend((a,b)))
    if not out["predictions_count"]:return None
    shadow=archive.enc(out)
    raw=archive.seal(export_raw,shadow,clock_fn())
    if archive.verify_replay(export_raw,shadow,*captures)!=out["predictions_count"]:raise ValueError("RAW_REPLAY_COUNT")
    return raw
def settle_due(db,*,capture_fn,clock_fn):
    now=clock_fn()
    due=[(mid,ko) for mid,ko in db.execute("""SELECT f.mid,f.ko FROM v32_fixtures f
        WHERE NOT EXISTS(SELECT 1 FROM v32_results r WHERE r.mid=f.mid)
        ORDER BY f.ko,f.mid""") if utc(ko)+timedelta(hours=2)<=now]
    reasons=Counter();settled=0;requests=0
    # Scope is fixed by the current portable model; historical seasons cannot enter V27.
    ids=[mid for mid,ko in due if "2026-07-01"<=ko[:10]<"2027-07-01"][:MAX_DUE]
    if ids:
        requests=1
        try:
            raw,meta=capture_fn("openligadb",2026)
            end=clock_fn()
            if end<now:raise ValueError("CYCLE_CLOCK_REVERSED")
            obs,lookup=validate_capture(raw,meta,2026,end)
        except ERRORS:
            reasons["SOURCE_UNAVAILABLE_OR_INVALID"]+=len(ids)
        else:
            for mid in ids:
                if mid not in lookup:reasons["MISSING_EVENT"]+=1;continue
                if lookup[mid]["matchIsFinished"] is not True:reasons["NOT_FINISHED"]+=1;continue
                try:
                    result=ledger.settle(db,mid,raw,obs,end)
                    if result["duplicate"]:reasons["ALREADY_SETTLED"]+=1
                    else:settled+=1
                except ERRORS:reasons["FIXTURE_REVIEW_REQUIRED"]+=1
    return {"due":len(due),"attempted":len(ids),"newly_settled":settled,"deferred":len(due)-len(ids),"requests":requests,"reasons":dict(reasons)}
def tick(db,export_raw,expected,*,producer=produce,capture_fn=capture,clock_fn=clock):
    exp=preflight(export_raw,expected)
    init(db);out={}
    for kind in INTERVALS:
        started=reserve(db,kind,clock_fn())
        if started is None:out[kind]={"state":"THROTTLED"};continue
        if kind=="forecast":
            try:
                raw=producer(exp,export_raw,capture_fn=capture_fn,clock_fn=clock_fn)
                if raw is None:out[kind]={"state":"NO_ELIGIBLE_FIXTURES"}
                else:
                    record=archive.audit(raw,sha(raw))
                    if record["input_sha256"][0]!=expected:raise ValueError("ARCHIVE_EXPORT_BINDING")
                    entry=ledger.register(db,raw,sha(raw),clock_fn())
                    out[kind]={"state":"SEALED","registration":entry,"archive_sha256":sha(raw)}
            except ERRORS as exc:
                reason=str(exc)
                out[kind]={"state":"HOLD_FORECAST_FAILED","reason":reason if re.fullmatch("[A-Z][A-Z0-9_]{1,100}",reason) else type(exc).__name__}
        else:
            q=settle_due(db,capture_fn=capture_fn,clock_fn=clock_fn)
            out[kind]={"state":"HOLD_PENDING_REVIEW" if q["reasons"] or q["deferred"] else "CHECKED","cycle":q}
        complete(db,kind,started,out[kind]["state"],clock_fn())
    return {"schema":"v34-stack-shadow-runner-v1","tasks":out,"health":health(db,clock_fn()),"ledger":ledger.report(db),
        "export_sha256":expected,"maximum_public_requests_per_tick":3,"forecast_interval_hours":6,"settlement_interval_hours":1,
        "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser()
    for k in ("state-dir","export","export-sha256"):p.add_argument("--"+k,required=True)
    a=p.parse_args();root=Path(a.state_dir)
    if not root.is_dir() or root.is_symlink() or root.stat().st_mode&0o077:raise ValueError("PRIVATE_STATE_DIRECTORY_REQUIRED")
    fd=os.open(root/"stack-runner.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"rb+") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        db=ledger.open_ledger(root/"stack.sqlite")
        try:out=tick(db,ledger.read(a.export),a.export_sha256)
        finally:db.close()
        print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
