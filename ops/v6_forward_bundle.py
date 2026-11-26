"""V6 unified forward research output contract, not release authorization.
Only local run artifacts are consumed; no network, odds, or historic rewriting.
"""
import argparse
import hashlib
import json
import math
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, timedelta
from pathlib import Path
from ops.v5_ensemble_competition import NAMES, vec, blend
from ops.v5_integration_acceptance import grid, project, summary

SCOPES={"bl1":"bundesliga","bl2":"bundesliga2","bl3":"germany_liga3"}
WEIGHTS={k:.5 if k=="joint_poisson" else 1/12 for k in NAMES}
LINES=(("handicap","home",-.25),("handicap","away",.25),("totals","over",2.25),("totals","under",2.25))
def utc(s):
    if not isinstance(s,str):raise ValueError("BAD_CLOCK")
    t=datetime.fromisoformat(s.replace("Z","+00:00"))
    if t.utcoffset() is None:raise ValueError("NAIVE_CLOCK")
    return t.astimezone(timezone.utc)
def digest(s):
    if not isinstance(s,str) or len(s)!=64 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError("BAD_DIGEST")
    return s
def native(s):
    if not isinstance(s,str) or not s.isascii() or not s.isdecimal() or not 0<int(s)<2**63 or s!=str(int(s)):
        raise ValueError("BAD_NATIVE_ID")
    return s
def decode(raw):
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError("DUPLICATE_JSON_KEY")
            out[k]=v
        return out
    def invalid(_):raise ValueError("NONFINITE_JSON")
    return json.loads(raw,object_pairs_hook=unique,parse_constant=invalid)

def pack(reports,now):
    if now.utcoffset() is None:raise ValueError("NAIVE_CLOCK")
    if set(reports)!=set(SCOPES):raise ValueError("MISSING_SCOPE")
    out=[];seen=set();pairs=set();coverage=[]
    for key,league in SCOPES.items():
        r=reports[key]
        if r["league"]!=league or r["provider_league_shortcut"]!=key or r["provider"]!="OpenLigaDB" or r["production_recommendations"]!="DISABLED" or r["verified_forward_sample_credit"]!=0 or r["automatic_promotion"] is not False:
            raise ValueError("UNSAFE_SOURCE")
        if r.get("schema")!="v5-native-forward-shadow-v1" or any(r.get(k) is not False for k in ("source_independent","result_authentication","external_capture_witness_verified","feature_availability_independently_verified","market_odds_available")):
            raise ValueError("INVALID_SOURCE_CONTRACT")
        if r["weights"]!=WEIGHTS or any(type(v) not in (int,float) for v in r["weights"].values()):raise ValueError("WEIGHT_MISMATCH")
        if type(r["verified_forward_sample_credit"]) is not int:raise ValueError("BAD_SAMPLE_CREDIT")
        generated=utc(r["generated_utc"])
        if not 0<=(now-generated).total_seconds()<=1800:raise ValueError("STALE_RUN")
        rows=r["predictions"]
        if not isinstance(rows,list) or type(r["predictions_count"]) is not int or len(rows)!=r["predictions_count"] or len(rows)>40:raise ValueError("BAD_COUNT")
        scheduled=r.get("scheduled_in_window")
        if scheduled is not None and (type(scheduled) is not int or not len(rows)<=scheduled<=400):raise ValueError("BAD_SCHEDULE_COUNT")
        if rows and scheduled is None:raise ValueError("MISSING_SCHEDULE_COUNT")
        if r["status"] not in ("HOLD","SHADOW_ONLY") or bool(rows)!=(r["status"]=="SHADOW_ONLY"):raise ValueError("BAD_STATUS")
        coverage.append({"league":league,"status":r["status"],"predictions":len(rows),"scheduled":r.get("scheduled_in_window"),"reason":r.get("reason")})
        if not rows:continue
        receipts=r["source_receipts"]
        if not isinstance(receipts,list) or len(receipts)!=2:raise ValueError("BAD_RECEIPTS")
        local=generated.astimezone(ZoneInfo("Europe/Berlin"))
        if type(r["season"]) is not int or r["season"]!=local.year-int(local.month<7):raise ValueError("BAD_SEASON")
        captures=[]
        for receipt,season in zip(receipts,(r["season"]-1,r["season"])):
            if receipt["source"]!=f"https://api.openligadb.de/getmatchdata/{key}/{season}":raise ValueError("SOURCE_SCOPE")
            digest(receipt["sha256"])
            capture=utc(receipt["captured_utc"])
            if not 0<=(generated-capture).total_seconds()<=600:raise ValueError("BAD_CAPTURE_CLOCK")
            if type(receipt.get("bytes")) is not int or not 0<receipt["bytes"]<=3_000_000:raise ValueError("BAD_CAPTURE_SIZE")
            captures.append(capture)
        if captures[0]>captures[1]:raise ValueError("CAPTURE_ORDER")
        for row in rows:
            mid=native(row["provider_event_id"]);h=native(row["home_native_id"]);a=native(row["away_native_id"])
            if mid in seen or h==a or row["production_recommendations"]!="DISABLED":raise ValueError("DUPLICATE_OR_UNSAFE")
            seen.add(mid)
            pair=(key,h,a)
            if pair in pairs:raise ValueError("DUPLICATE_NATIVE_PAIR")
            pairs.add(pair)
            allowed={"provider_event_id","home_native_id","away_native_id","home","away","prediction_utc","kickoff_utc","p_1x2","model_probabilities","joint_goal_rates","joint_rates_are_not_ensemble_goal_distribution","production_recommendations"}
            if set(row)!=allowed:raise ValueError("UNEXPECTED_OR_MISSING_FORECAST_FIELD")
            if row["joint_rates_are_not_ensemble_goal_distribution"] is not True:raise ValueError("UNSAFE_DISTRIBUTION_FLAG")
            if any(not isinstance(row[k],str) or not 0<len(row[k].strip())<=109 for k in ("home","away")):raise ValueError("BAD_LABEL")
            stamp=utc(row["prediction_utc"]);ko=utc(row["kickoff_utc"])
            if stamp>generated or (generated-stamp).total_seconds()>10 or ko<=now+timedelta(minutes=10) or ko>stamp+timedelta(days=7) or max(captures)>stamp:raise ValueError("BAD_FORECAST_CLOCK")
            if not datetime(r["season"],7,1,tzinfo=timezone.utc)<=ko<datetime(r["season"]+1,7,1,tzinfo=timezone.utc):raise ValueError("KICKOFF_OUTSIDE_SEASON")
            v=row["model_probabilities"]
            if set(v)!=set(NAMES):raise ValueError("MISSING_MODEL")
            v={k:vec(p) for k,p in v.items()}
            p=vec(row["p_1x2"])
            if max(abs(x-y) for x,y in zip(p,blend(v,WEIGHTS)))>1e-8:raise ValueError("ENSEMBLE_MISMATCH")
            rates=row["joint_goal_rates"]
            if not isinstance(rates,list) or len(rates)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or not .05<=v<=8 for v in rates):raise ValueError("BAD_JOINT_RATES")
            g=grid(0,0,*rates);s=summary(g)
            if max(abs(x-y) for x,y in zip(s["1x2"],v["joint_poisson"]))>1e-5:raise ValueError("SCORE_GRID_MISMATCH")
            out.append({"league":league,"provider_event_id":mid,"home_native_id":h,"away_native_id":a,
                "home":row["home"],"away":row["away"],"prediction_utc":stamp.isoformat(),"kickoff_utc":ko.isoformat(),
                "source_receipts":receipts,"ensemble_1x2":p,"model_probabilities":v,
                "joint_poisson_score_distribution":s,"joint_goal_rates":rates,
                "joint_only_fixed_line_scenarios":[{"kind":k,"side":side,"line":line,"probabilities":project(g,k,side,line)} for k,side,line in LINES],
                "actual_market_line_verified":False,"production_recommendations":"DISABLED"})
    return {"schema":"v6-unified-forward-shadow-v1","generated_utc":now.isoformat(),"status":"HOLD",
            "production_recommendations":"DISABLED","verified_forward_sample_credit":0,
            "independent_capture_witness_verified":False,"actual_market_odds_verified":False,
            "ensemble_distribution_not_inferred":True,"coverage":coverage,"predictions_count":len(out),"predictions":out}
def main():
    p=argparse.ArgumentParser();p.add_argument("--input-dir",required=True);p.add_argument("--output",required=True);a=p.parse_args()
    reports={};hashes={}
    for key in SCOPES:
        f=Path(a.input_dir)/f"native-{key}.json"
        if not 0<f.stat().st_size<=2_000_000:raise ValueError("INPUT_SIZE")
        raw=f.read_bytes();reports[key]=decode(raw);hashes[key]=hashlib.sha256(raw).hexdigest()
    result=pack(reports,datetime.now(timezone.utc));result["input_artifact_sha256"]=hashes
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!="predictions"}))
if __name__=="__main__":main()
