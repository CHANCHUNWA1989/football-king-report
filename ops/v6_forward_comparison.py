"""V6.2 same-fixture forward comparison. Research only; no certified evidence."""
import argparse
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from ops.v6_forward_bundle import utc,decode,native,digest
from ops.v6_calibration_challenger import calibrate, CUT
from ops.v5_ensemble_competition import vec,metrics
from ops.v5_native_bundesliga_forward import normalize

def sha(raw):return hashlib.sha256(raw).hexdigest()
def seal(bundle,cal,now):
    if bundle.get("schema")!="v6-unified-forward-shadow-v1" or cal.get("schema")!="v6-1-league-calibration-research-v1":raise ValueError("BAD_SCHEMA")
    if any(r.get("status")!="HOLD" or r.get("production_recommendations")!="DISABLED" for r in (bundle,cal)):raise ValueError("UNSAFE_INPUT")
    if bundle.get("verified_forward_sample_credit")!=0 or cal.get("automatic_promotion") is not False or cal.get("prospective_validation") is not False or cal.get("cutoff")!=CUT:raise ValueError("UNSAFE_FLAGS")
    generated=utc(bundle["generated_utc"])
    if not 0<=(now-generated).total_seconds()<=600:raise ValueError("STALE_BUNDLE")
    par=cal["per_league"]["de.1"]["params"]
    # Validate frozen grid membership even if no eligible upcoming fixtures.
    calibrate([.4,.3,.3],*par)
    rows=[];seen=set()
    for r in bundle["predictions"]:
        if r["league"]!="bundesliga":continue
        mid=native(r["provider_event_id"]);h=native(r["home_native_id"]);a=native(r["away_native_id"])
        ko=utc(r["kickoff_utc"]);forecast=utc(r["prediction_utc"])
        if mid in seen or h==a or r["production_recommendations"]!="DISABLED":raise ValueError("BAD_IDENTITY")
        seen.add(mid)
        if not forecast<=generated<=now or ko<=now+timedelta(minutes=10):raise ValueError("BAD_FORECAST_CLOCK")
        if any(utc(x["captured_utc"])>forecast for x in r["source_receipts"]):raise ValueError("LATE_SOURCE")
        p=vec(r["ensemble_1x2"])
        rows.append({"provider_event_id":mid,"home_native_id":h,"away_native_id":a,"kickoff_utc":ko.isoformat(),
            "prediction_utc":forecast.isoformat(),"baseline":p,"candidate":calibrate(p,*par)})
    return {"schema":"v6-2-forward-comparison-v1","league":"bundesliga","provider":"OpenLigaDB",
        "calibration_params":par,"calibration_development_cutoff":CUT,"sealed_utc":now.isoformat(),
        "historical_assessment_previously_inspected":True,"external_capture_witness_verified":False,
        "production_recommendations":"DISABLED","verified_forward_sample_credit":0,"status":"HOLD","rows":rows}

def score(record,results,observed):
    if record.get("schema")!="v6-2-forward-comparison-v1" or record.get("league")!="bundesliga" or record.get("provider")!="OpenLigaDB" or record.get("production_recommendations")!="DISABLED" or record.get("verified_forward_sample_credit")!=0:raise ValueError("UNSAFE_RECORD")
    sealed=utc(record["sealed_utc"])
    if observed<=sealed:raise ValueError("RESULT_CLOCK")
    rows=record["rows"];seen=set();matched=[];pending=0
    if not rows:return {"n":0,"status":"HOLD","verified_forward_sample_credit":0,"production_recommendations":"DISABLED"}
    year=utc(rows[0]["kickoff_utc"]).year-int(utc(rows[0]["kickoff_utc"]).month<7)
    # Reuse strict native season parser; no additional network calls.
    normalize(results,year,observed,shortcut="bl1")
    lookup={str(r["matchID"]):r for r in results}
    for r in rows:
        mid=native(r["provider_event_id"]);ko=utc(r["kickoff_utc"])
        if mid in seen or not utc(r["prediction_utc"])<=sealed<ko-timedelta(minutes=10):raise ValueError("INVALID_SEAL")
        seen.add(mid)
        b=vec(r["baseline"]);c=vec(r["candidate"])
        if max(abs(x-y) for x,y in zip(c,calibrate(b,*record["calibration_params"])))>1e-8:raise ValueError("CANDIDATE_MISMATCH")
        x=lookup.get(mid)
        if x is None:pending+=1;continue
        if (str(x["team1"]["teamId"]),str(x["team2"]["teamId"]),utc(x["matchDateTimeUTC"]))!=(r["home_native_id"],r["away_native_id"],ko):raise ValueError("IDENTITY_CONFLICT")
        if x["matchIsFinished"] is not True or observed<ko+timedelta(hours=2):pending+=1;continue
        ft=[z for z in x["matchResults"] if z["resultTypeID"]==2]
        if len(ft)!=1:raise ValueError("BAD_FINAL")
        h,a=ft[0]["pointsTeam1"],ft[0]["pointsTeam2"]
        matched.append({"id":mid,"y":0 if h>a else 1 if h==a else 2,"baseline":b,"candidate":c})
    return {"schema":"v6-2-forward-comparison-score-v1","n":len(matched),"pending":pending,
        "baseline":metrics(matched,lambda r:r["baseline"]),"candidate":metrics(matched,lambda r:r["candidate"]),
        "single_provider_results":True,"external_capture_witness_verified":False,"market_comparison_available":False,
        "verified_forward_sample_credit":0,"production_recommendations":"DISABLED","status":"HOLD"}

def read(path):
    f=Path(path)
    if not 0<f.stat().st_size<=3_000_000:raise ValueError("INPUT_SIZE")
    raw=f.read_bytes();return decode(raw),sha(raw)
def main():
    p=argparse.ArgumentParser();p.add_argument("mode",choices=("seal","score"));p.add_argument("--input",required=True);p.add_argument("--other",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    x,h=read(a.input);y,j=read(a.other);now=datetime.now(timezone.utc)
    out=seal(x,y,now) if a.mode=="seal" else score(x,y,now)
    out["input_sha256"]=[h,j]
    with Path(a.output).open("x") as f:json.dump(out,f,indent=2,allow_nan=False)
    print(json.dumps({**{k:v for k,v in out.items() if k!="rows"},"sealed_count":len(out.get("rows",[]))},allow_nan=False))
if __name__=="__main__":main()
