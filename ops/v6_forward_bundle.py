"""V6 unified forward research output contract, not release authorization.
Only local run artifacts are consumed; no network, odds, or historic rewriting.
"""
import argparse
import hashlib
import json
import math
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
def pack(reports,now):
    if now.utcoffset() is None:raise ValueError("NAIVE_CLOCK")
    if set(reports)!=set(SCOPES):raise ValueError("MISSING_SCOPE")
    out=[];seen=set();coverage=[]
    for key,league in SCOPES.items():
        r=reports[key]
        if r["league"]!=league or r["provider_league_shortcut"]!=key or r["provider"]!="OpenLigaDB" or r["production_recommendations"]!="DISABLED" or r["verified_forward_sample_credit"]!=0 or r["automatic_promotion"] is not False:
            raise ValueError("UNSAFE_SOURCE")
        if r["weights"]!=WEIGHTS:raise ValueError("WEIGHT_MISMATCH")
        generated=utc(r["generated_utc"])
        if not 0<=(now-generated).total_seconds()<=1800:raise ValueError("STALE_RUN")
        rows=r["predictions"]
        if not isinstance(rows,list) or len(rows)!=r["predictions_count"] or len(rows)>40:raise ValueError("BAD_COUNT")
        if r["status"] not in ("HOLD","SHADOW_ONLY") or bool(rows)!=(r["status"]=="SHADOW_ONLY"):raise ValueError("BAD_STATUS")
        coverage.append({"league":league,"status":r["status"],"predictions":len(rows),"scheduled":r.get("scheduled_in_window"),"reason":r.get("reason")})
        if not rows:continue
        receipts=r["source_receipts"]
        if len(receipts)!=2:raise ValueError("BAD_RECEIPTS")
        for receipt,season in zip(receipts,(r["season"]-1,r["season"])):
            if receipt["source"]!=f"https://api.openligadb.de/getmatchdata/{key}/{season}":raise ValueError("SOURCE_SCOPE")
            digest(receipt["sha256"])
            if not 0<=(generated-utc(receipt["captured_utc"])).total_seconds()<=600:raise ValueError("BAD_CAPTURE_CLOCK")
        for row in rows:
            mid=native(row["provider_event_id"]);h=native(row["home_native_id"]);a=native(row["away_native_id"])
            if mid in seen or h==a or row["production_recommendations"]!="DISABLED":raise ValueError("DUPLICATE_OR_UNSAFE")
            seen.add(mid)
            if any(row.get(k) is not None for k in ("score_ft","result","outcome","y")):raise ValueError("RESULT_BEARING")
            stamp=utc(row["prediction_utc"]);ko=utc(row["kickoff_utc"])
            if stamp>generated or (generated-stamp).total_seconds()>10 or ko<=now+timedelta(minutes=10):raise ValueError("BAD_FORECAST_CLOCK")
            v=row["model_probabilities"]
            if set(v)!=set(NAMES):raise ValueError("MISSING_MODEL")
            v={k:vec(p) for k,p in v.items()}
            p=vec(row["p_1x2"])
            if max(abs(x-y) for x,y in zip(p,blend(v,WEIGHTS)))>1e-8:raise ValueError("ENSEMBLE_MISMATCH")
            rates=row["joint_goal_rates"]
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
        raw=f.read_bytes();reports[key]=json.loads(raw);hashes[key]=hashlib.sha256(raw).hexdigest()
    result=pack(reports,datetime.now(timezone.utc));result["input_artifact_sha256"]=hashes
    with Path(a.output).open("x",encoding="utf-8") as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps({k:v for k,v in result.items() if k!="predictions"}))
if __name__=="__main__":main()
