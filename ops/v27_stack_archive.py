"""V27 same-cut native stack archive. Local integrity is not independent evidence.
No market data, verified EV, or production permission.
"""
import argparse,io,json,math
from datetime import datetime,timezone,timedelta
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from ops import v25_native_stack as stack,v9_stacking_research as s,v9_league_weights as w
from ops import v5_ensemble_competition as e
from ops.v6_forward_bundle import decode,digest,native,utc,WEIGHTS
from ops.v20_signed_receipts import bounded,sha
from ops.v21_raw_results import verify_result
from ops.v23_forward_cycle import validate_capture

LIMIT=3_000_000
FILES=("record.json","export.json","shadow.json")
MODELS=("v5","v10","v10_1")
def enc(d):return json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def safe(d):
    if d.get("status")!="HOLD" or d.get("production_recommendations")!="DISABLED" or type(d.get("verified_forward_sample_credit")) is not int or d["verified_forward_sample_credit"]!=0 or d.get("automatic_promotion") is not False:
        raise ValueError("UNSAFE_RESEARCH_INPUT")
def equal(a,b):
    if max(abs(x-y) for x,y in zip(e.vec(a),e.vec(b)))>1e-9:raise ValueError("PROBABILITY_MISMATCH")
def make_record(export_raw,shadow_raw,now):
    model=decode(bounded(export_raw,LIMIT));src=decode(bounded(shadow_raw,LIMIT));safe(model);safe(src)
    if model["schema"]!="v25-portable-stack-export-v1" or src["schema"]!="v25-native-stack-shadow-v1":raise ValueError("SCHEMA")
    if src.get("reason") or src.get("date_convention")!="Asia/Hong_Kong":raise ValueError("SHADOW_UNAVAILABLE")
    if src.get("future_intervening_results_unknown") is not True or src.get("native_historical_identity_crosswalk_verified") is not False:raise ValueError("SHADOW_FLAGS")
    stamp=utc(src["generated_utc"]);asof=utc(src["inference_as_of_utc"])
    if not asof<=stamp<=now<=stamp+timedelta(minutes=10) or stamp-asof>timedelta(minutes=10):raise ValueError("SEAL_CLOCK")
    receipts=src["source_receipts"]
    if type(receipts) is not list or len(receipts)!=2:raise ValueError("SOURCE_RECEIPTS")
    captures=[]
    for q,year in zip(receipts,(2025,2026)):
        if q["provider"]!="openligadb" or q["season"]!=year or q["source"]!=f"https://api.openligadb.de/getmatchdata/bl1/{year}" or q["source_authenticated"] is not False:raise ValueError("SOURCE_SCOPE")
        digest(q["sha256"]);t=utc(q["captured_utc"]);captures.append(t)
        if not asof-timedelta(minutes=15)<=t<=asof or type(q["bytes"]) is not int or not 0<q["bytes"]<=LIMIT:raise ValueError("SOURCE_CLOCK")
    if captures[0]>captures[1]:raise ValueError("CAPTURE_ORDER")
    m=model["model"];rows=src["predictions"]
    if type(rows) is not list or type(src["predictions_count"]) is not int or src["predictions_count"]!=len(rows) or not 0<len(rows)<=40:raise ValueError("EMPTY_OR_BAD_COUNT")
    seen=set();pairs=set();out=[]
    allowed={"event_id","h","a","kickoff_utc","home","away","experts","v10_weights","v10_prior_n","v10_reference","v10_1_stack","prediction_utc"}
    for r in rows:
        if set(r)!=allowed:raise ValueError("FORECAST_FIELDS")
        mid,h,a=map(native,(r["event_id"],r["h"],r["a"]))
        ko=utc(r["kickoff_utc"])
        if mid in seen or (h,a) in pairs or h==a:raise ValueError("FIXTURE_DUPLICATE")
        seen.add(mid);pairs.add((h,a))
        if utc(r["prediction_utc"])!=stamp or not now+timedelta(minutes=10)<ko<=stamp+timedelta(days=7) or not datetime(2026,7,1,tzinfo=timezone.utc)<=ko<datetime(2027,7,1,tzinfo=timezone.utc):raise ValueError("FORECAST_CLOCK")
        if any(type(r[k]) is not str or not 0<len(r[k].strip())<=109 for k in ("home","away")):raise ValueError("TEAM_LABEL")
        q=r["experts"];weights=r["v10_weights"];n=r["v10_prior_n"]
        if set(q)!=set(s.EXPERTS) or set(weights)!=set(s.EXPERTS) or type(n) is not int or not 0<=n<=w.WINDOW:raise ValueError("EXPERT_CONTRACT")
        q={k:e.vec(q[k]) for k in s.EXPERTS}
        if any(type(x) not in (int,float) or not math.isfinite(x) or not (1-w.SHRINK)*w.ANCHOR[k]-1e-12<=x<=1 for k,x in weights.items()) or abs(math.fsum(weights.values())-1)>1e-9:raise ValueError("WEIGHT_CONTRACT")
        if n<w.MIN_HISTORY and weights!=w.ANCHOR:raise ValueError("ANCHOR_CONTRACT")
        p=e.vec([math.fsum(weights[k]*q[k][i] for k in s.EXPERTS) for i in range(3)])
        equal(p,r["v10_reference"])
        z=s.combine(stack.portable(m,{"experts":q}),p,m["temperature"],m["stack_weight"])
        equal(z,r["v10_1_stack"])
        out.append({"fixture_id":mid,"home_id":h,"away_id":a,"kickoff_utc":ko.isoformat(),
            "v5":e.blend({k:q[k] for k in e.NAMES},WEIGHTS),"v10":p,"v10_1":z})
    return {"schema":"v27-native-stack-comparison-v1","sealed_utc":now.isoformat(),"input_sha256":[sha(export_raw),sha(shadow_raw)],
        "rows":out,"same_cut_baseline":True,"raw_feature_replay_in_archive":False,
        "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def verify_replay(export_raw,shadow_raw,old,new):
    """Recompute actual expert history and predictions from matching private bytes."""
    m=decode(export_raw);src=decode(shadow_raw);asof=utc(src["inference_as_of_utc"]);stamp=utc(src["generated_utc"])
    for raw,receipt,year in zip((old,new),src["source_receipts"],(2025,2026)):validate_capture(raw,receipt,year,asof)
    out=stack.infer(m,decode(old),decode(new),asof)
    rows=[r for r in out["predictions"] if utc(r["kickoff_utc"])>stamp+timedelta(minutes=10)]
    for r in rows:r["prediction_utc"]=stamp.isoformat()
    # Native deterministic estimators may differ at machine precision. Compare probabilities by tolerance.
    a={r["event_id"]:r for r in rows};b={r["event_id"]:r for r in src["predictions"]}
    if len(a)!=len(rows) or len(b)!=len(src["predictions"]) or set(a)!=set(b):raise ValueError("REPLAY_COVERAGE")
    for mid,r in a.items():
        v=b[mid]
        for k in set(r)-{"experts","v10_weights","v10_reference","v10_1_stack"}:
            if r[k]!=v[k]:raise ValueError("REPLAY_IDENTITY")
        for k in s.EXPERTS:
            equal(r["experts"][k],v["experts"][k])
            if abs(r["v10_weights"][k]-v["v10_weights"][k])>1e-9:raise ValueError("REPLAY_WEIGHT")
        for k in ("v10_reference","v10_1_stack"):equal(r[k],v[k])
    return len(rows)
def seal(export_raw,shadow_raw,now):
    record=make_record(export_raw,shadow_raw,now)
    f=io.BytesIO()
    with ZipFile(f,"w",compression=ZIP_DEFLATED) as z:
        for name,raw in zip(FILES,(enc(record),export_raw,shadow_raw)):z.writestr(name,raw)
    return bounded(f.getvalue(),LIMIT)
def audit(raw,expected):
    bounded(raw,LIMIT)
    if sha(raw)!=digest(expected):raise ValueError("ARCHIVE_DIGEST")
    with ZipFile(io.BytesIO(raw)) as z:
        if len(z.namelist())!=3 or set(z.namelist())!=set(FILES):raise ValueError("ARCHIVE_MEMBERS")
        if any(not 0<z.getinfo(k).file_size<=LIMIT for k in FILES):raise ValueError("ARCHIVE_SIZE")
        rec,exp,shadow=(z.read(k) for k in FILES)
    d=decode(rec);rebuilt=make_record(exp,shadow,utc(d["sealed_utc"]))
    if d!=rebuilt:raise ValueError("ARCHIVE_RECORD_MISMATCH")
    return d
def score(raw,expected,result_raw,observed):
    d=audit(raw,expected)
    bounded(result_raw,LIMIT)
    if observed<=utc(d["sealed_utc"]):raise ValueError("RESULT_CLOCK")
    doc=decode(result_raw)
    if type(doc) is not list:raise ValueError("RESULT_FORMAT")
    lookup={}
    for r in doc:
        mid=native(str(r["matchID"]))
        if mid in lookup:raise ValueError("RESULT_DUPLICATE")
        lookup[mid]=r
    out=[];pending=0
    for r in d["rows"]:
        mid=r["fixture_id"];x=lookup.get(mid)
        if x is None or x.get("matchIsFinished") is not True or observed<utc(r["kickoff_utc"])+timedelta(hours=2):pending+=1;continue
        q=verify_result(result_raw,"openligadb",fixture_id=mid,home_id=r["home_id"],away_id=r["away_id"],kickoff_utc=r["kickoff_utc"],observed_utc=observed.isoformat())
        h,a=q["score"];out.append({**r,"y":0 if h>a else 1 if h==a else 2})
    return {"schema":"v27-same-cut-score-v1","n":len(out),"pending":pending,"metrics":{k:e.metrics(out,lambda r:r[k]) for k in MODELS},
        "archive_sha256":expected,"result_sha256":sha(result_raw),"single_source_research_only":True,
        "verified_forward_sample_credit":0,"automatic_promotion":False,"production_recommendations":"DISABLED","status":"HOLD"}
def main():
    p=argparse.ArgumentParser();p.add_argument("--archive",required=True);p.add_argument("--sha256",required=True)
    p.add_argument("--results");p.add_argument("--observed-utc");a=p.parse_args()
    raw=Path(a.archive).read_bytes()
    if bool(a.results)!=bool(a.observed_utc):raise ValueError("RESULT_ARGUMENTS")
    if a.results:
        now=utc(a.observed_utc)
        if now>datetime.now(timezone.utc):raise ValueError("FUTURE_RESULT")
        out=score(raw,a.sha256,Path(a.results).read_bytes(),now)
    else:out=audit(raw,a.sha256)
    print(json.dumps(out,allow_nan=False))
if __name__=="__main__":main()
