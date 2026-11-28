"""Seal the opponent-adjusted candidate using its own computation clock.

The public site is unchanged. Only the archive copy receives this research
object; existing whole-shadow signatures can cover it, not certify its merits.
"""
import argparse
import hashlib
import json
import math
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .opponent_adjusted_research import build,MODEL,HALF_LIFE,PRIOR,ITERATIONS,poisson_1x2
except ImportError:
    from opponent_adjusted_research import build,MODEL,HALF_LIFE,PRIOR,ITERATIONS,poisson_1x2

TOP_KEY="opponent_adjusted_forward_challenger"
SCHEMA="football-king-opponent-adjusted-forward-v1"
HK=ZoneInfo("Asia/Hong_Kong")
MAX_BYTES=8_000_000


def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")


def binding(shadow):
    return hashlib.sha256(canonical({k:shadow[k] for k in
        ("schema","as_of_utc","predictions_count","predictions","production_recommendations")})).hexdigest()


def utc(value):
    t=datetime.fromisoformat(value)
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIME")
    return t.astimezone(timezone.utc)


def capture(shadow,finished,clock=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    start=clock()
    result=build(shadow,finished,start)
    completed=clock()
    rows=[]
    out={"schema":SCHEMA,"model":MODEL,"status":"HOLD",
         "production_recommendations":"DISABLED","automatic_model_promotion":False,
         "independently_verified":False,"positive_ev_verified":False,
         "recommendation_count":0,"source_as_of_utc":shadow.get("as_of_utc"),
         "started_utc":start.isoformat(),"generated_utc":completed.isoformat(),
         "source_predictions_sha256":binding(shadow),"predictions":rows,
         "predictions_count":0,"parameters":result["parameters"],
         "clock_is_external_witness":False,"reconstructed_after_kickoff":False}
    source=utc(shadow["as_of_utc"])
    if not (source<=start<=completed<=source+timedelta(minutes=30)
            and source.astimezone(HK).date()==completed.astimezone(HK).date()):
        return out
    originals={(r["league"],r["event_id"]):r for r in shadow["predictions"]
               if isinstance(r,dict) and isinstance(r.get("league"),str) and isinstance(r.get("event_id"),str)}
    for row in result["predictions"]:
        if utc(row["kickoff_utc"])<=completed+timedelta(minutes=10):
            continue
        original=originals[(row["league"],row["event_id"])]
        rows.append({**row,"home":original["home"],"away":original["away"],
            "original_prediction_utc":original["prediction_utc"],
            "candidate_prediction_utc":completed.isoformat()})
    out["predictions_count"]=len(rows)
    if rows:
        out["status"]="FORWARD_RESEARCH_CAPTURE_ONLY"
    return out


def attach(shadow,record):
    if TOP_KEY in shadow:
        raise ValueError("PRIOR_CAPTURE")
    if (record.get("schema")!=SCHEMA or record.get("model")!=MODEL
        or record.get("source_predictions_sha256")!=binding(shadow)
        or record.get("source_as_of_utc")!=shadow["as_of_utc"]
        or record.get("production_recommendations")!="DISABLED"
        or record.get("automatic_model_promotion") is not False
        or record.get("independently_verified") is not False
        or record.get("positive_ev_verified") is not False
        or record.get("recommendation_count")!=0
        or record.get("predictions_count")!=len(record["predictions"])):
        raise ValueError("INVALID_CAPTURE")
    generated=utc(record["generated_utc"])
    started=utc(record["started_utc"])
    source=utc(shadow["as_of_utc"])
    rows=record["predictions"]
    if (not isinstance(rows,list) or len(rows)>3000
        or record.get("status")!=("FORWARD_RESEARCH_CAPTURE_ONLY" if rows else "HOLD")
        or record.get("parameters")!={"half_life_days":HALF_LIFE,"prior_goal_exposure":PRIOR,"iterations":ITERATIONS}
        or record.get("clock_is_external_witness") is not False
        or record.get("reconstructed_after_kickoff") is not False):
        raise ValueError("INVALID_CAPTURE_STATE")
    if rows and not (source<=started<=generated<=source+timedelta(minutes=30)
        and source.astimezone(HK).date()==generated.astimezone(HK).date()):
        raise ValueError("INVALID_CAPTURE_CLOCK")
    originals={}
    for p in shadow["predictions"]:
        key=(p["league"],p["event_id"])
        if key in originals:
            originals[key]=None
        else:
            originals[key]=p
    seen=set()
    for r in rows:
        key=(r["league"],r["event_id"])
        p=originals.get(key)
        if (p is None or key in seen or r.get("production_recommendations")!="DISABLED"
            or any(r[k]!=p[k] for k in ("home","away","kickoff_utc","training_games"))
            or r["training_sha256"]!=p["training_observations_sha256"]
            or r["original_prediction_utc"]!=p["prediction_utc"]
            or r["original"]!=[p["p_home"],p["p_draw"],p["p_away"]]
            or utc(r["kickoff_utc"])<=generated+timedelta(minutes=10)
            or r["candidate_prediction_utc"]!=record["generated_utc"]):
            raise ValueError("INVALID_CAPTURE_ROW")
        rates=(r["expected_home_goals"],r["expected_away_goals"])
        if not all(type(v) in (float,int) and math.isfinite(v) and .1<=v<=5.5 for v in rates):
            raise ValueError("INVALID_CAPTURE_RATES")
        if r["p"]!=list(poisson_1x2(*rates)):
            raise ValueError("INVALID_CAPTURE_PROBABILITIES")
        seen.add(key)
    return {**shadow,TOP_KEY:record}


def load(path):
    def unique(pairs):
        d={}
        for k,v in pairs:
            if k in d:
                raise ValueError("DUPLICATE_JSON_KEY")
            d[k]=v
        return d
    def reject(_):
        raise ValueError("NONFINITE_JSON")
    with Path(path).open("rb") as f:
        raw=f.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES:
        raise ValueError("INPUT_TOO_LARGE")
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)


def write(path,obj):
    raw=canonical(obj)+b"\n"
    if len(raw)>MAX_BYTES:
        raise ValueError("OUTPUT_TOO_LARGE")
    Path(path).write_bytes(raw)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shadow",required=True)
    p.add_argument("--finished")
    p.add_argument("--capture")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    if bool(a.finished)==bool(a.capture):
        p.error("choose exactly one of --finished or --capture")
    shadow=load(a.shadow)
    result=capture(shadow,load(a.finished)) if a.finished else attach(shadow,load(a.capture))
    write(a.output,result)
    print(json.dumps({"status":result.get("status"),"production_recommendations":"DISABLED",
                      "predictions_count":result.get("predictions_count") if a.finished else result[TOP_KEY]["predictions_count"]}))


if __name__=="__main__":
    main()
