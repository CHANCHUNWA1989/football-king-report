"""Connect the existing V4.1 shadow forecasts to one research score distribution.
No API calls, market price inference, fitted calibration, or production promotion.
"""
import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HK = ZoneInfo("Asia/Hong_Kong")
SCHEMA = "football-king-unified-shadow-integration-v1"


def utc(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIME")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return parsed.astimezone(timezone.utc)


GRADES = ("FULL_WIN", "HALF_WIN", "PUSH", "HALF_LOSS", "FULL_LOSS")
# Integer quarter-goal units. Fixed research grid, NOT observed market lines.
HANDICAP_Q = tuple(range(-12, 13))
TOTAL_Q = tuple(range(4, 21))


def score_matrix(h, a):
    if any(type(v) not in (int, float) or not math.isfinite(v)
           or not 0.1 <= v <= 5.5 for v in (h, a)):
        raise ValueError("INVALID_SHADOW_RATE")
    def pmf(rate):
        result = [math.exp(-rate)]
        for k in range(1, 41):
            result.append(result[-1] * rate / k)
        return result
    hp, ap = pmf(h), pmf(a)
    mass = math.fsum(hp) * math.fsum(ap)
    if abs(1 - mass) > 1e-10:
        raise ValueError("TRUNCATED_MASS")
    return [[x*y/mass for y in ap] for x in hp]


def marginal_scores(score):
    margin, total = Counter(), Counter()
    for i, row in enumerate(score):
        for j, p in enumerate(row):
            margin[i-j] += p
            total[i+j] += p
    return margin, total


def distribution_from_matrix(score, margin, total):
    home = math.fsum(v for k,v in margin.items() if k>0)
    draw = margin[0]
    away = math.fsum(v for k,v in margin.items() if k<0)
    over = math.fsum(v for k,v in total.items() if k>=3)
    btts = math.fsum(v for i,r in enumerate(score) for j,v in enumerate(r) if i and j)
    return {"p_home":home, "p_draw":draw, "p_away":away,
            "p_over_2_5":over, "p_under_2_5":1-over, "p_btts":btts}


def distribution(h, a):
    score = score_matrix(h, a)
    return distribution_from_matrix(score, *marginal_scores(score))


def settlement_grade(outcome, market, side, line_q):
    """Grade 90-minute margin or total against integer quarter-goal units."""
    if type(outcome) is not int or type(line_q) is not int:
        raise ValueError("INTEGER_QUARTER_UNITS_REQUIRED")
    if market == "HANDICAP" and side in ("HOME","AWAY") and line_q in HANDICAP_Q:
        adjusted = 4*outcome if side=="HOME" else -4*outcome
        def value(q):
            return adjusted+q
    elif market == "TOTAL" and side in ("OVER","UNDER") and line_q in TOTAL_Q and outcome>=0:
        def value(q):
            return (4*outcome-q) if side=="OVER" else (q-4*outcome)
    else:
        raise ValueError("INVALID_MARKET_SCENARIO")
    halves = (line_q-1,line_q+1) if line_q%2 else (line_q,line_q)
    signs = [(value(q)>0)-(value(q)<0) for q in halves]
    return GRADES[2-sum(signs)]


def scenario(marginal, market, side, line_q):
    out = dict.fromkeys(GRADES, 0.0)
    for k,p in marginal.items():
        out[settlement_grade(k,market,side,line_q)] += p
    if abs(math.fsum(out.values())-1)>1e-10:
        raise ValueError("INVALID_SCENARIO_MASS")
    return {"market":market,"side":side,"line_quarter_units":line_q,
            "outcome_probabilities":out,
            "hypothetical_line_not_market_quote":True}


def asian_scenarios(margin, total):
    result=[]
    for q in HANDICAP_Q:
        result.append(scenario(margin,"HANDICAP","HOME",q))
        result.append(scenario(margin,"HANDICAP","AWAY",-q))
    for q in TOTAL_Q:
        for side in ("OVER","UNDER"):
            result.append(scenario(total,"TOTAL",side,q))
    return result

def evaluate(shadow, collection, now):
    now = utc(now.isoformat())
    out = {"schema":SCHEMA, "as_of_utc":now.isoformat(),
           "status":"HOLD", "production_recommendations":"DISABLED",
           "model_calibrated":False, "executable_market_quotes":False,
           "positive_ev_verified":False, "recommendation_count":0,
           "source_model":"poisson-shrinkage-unvalidated-v4.1",
           "research_only":True, "rows":[], "rejected":{},
           "asian_lines_observed":False,"asian_scenario_grid_only":True,
           "market_collection_status":"UNKNOWN"}
    if isinstance(collection, dict) and collection.get("schema") == "football-king-free-market-collection-status-v1":
        if collection.get("collection_status") == "HOLD":
            out["market_collection_status"] = "HOLD"
        if collection.get("collection_reason") == "FREE_QUOTA_GUARD":
            out["market_collection_reason"] = "FREE_QUOTA_GUARD"
    try:
        if (not isinstance(shadow, dict) or shadow.get("schema") != "football-king-uncalibrated-shadow-1"
            or shadow.get("production_recommendations") != "DISABLED"
            or shadow.get("model_calibrated") is not False
            or shadow.get("status") != "SHADOW_ONLY"):
            raise ValueError("SHADOW_NOT_READY")
        captured = utc(shadow["as_of_utc"])
        if not timedelta(0) <= now-captured <= timedelta(minutes=30):
            raise ValueError("SHADOW_STALE_OR_FUTURE")
        rows = shadow["predictions"]
        if not isinstance(rows,list) or len(rows)>3000 or type(shadow.get("predictions_count")) is not int or shadow["predictions_count"] != len(rows):
            raise ValueError("INVALID_BATCH")
        counts = Counter((r.get("league"), r.get("event_id")) for r in rows
                         if isinstance(r,dict) and isinstance(r.get("league"),str)
                         and isinstance(r.get("event_id"),str))
    except (ValueError, KeyError, TypeError, OverflowError):
        out["reason"]="INVALID_OR_UNAVAILABLE_SHADOW_BATCH"
        return out
    rejects = Counter()
    for row in rows:
        try:
            if not isinstance(row,dict):
                raise ValueError("INVALID_ROW")
            league,event = row["league"],row["event_id"]
            if not all(isinstance(x,str) and 0<len(x)<=250 for x in (league,event)):
                raise ValueError("INVALID_IDENTITY")
            if counts[(league,event)] != 1:
                raise ValueError("DUPLICATE_IDENTITY")
            if row.get("model") != out["source_model"] or row.get("calibrated") is not False or row.get("production_recommendations")!="DISABLED":
                raise ValueError("INVALID_MODEL_STATE")
            pred, kick = utc(row["prediction_utc"]), utc(row["kickoff_utc"])
            if not pred <= captured <= now < kick or kick-now <= timedelta(minutes=10) or captured-pred > timedelta(minutes=30):
                raise ValueError("INVALID_PREMATCH_TIME")
            cutoff = date.fromisoformat(row["training_cutoff_local_day"])
            if cutoff >= pred.astimezone(HK).date():
                raise ValueError("TRAINING_CUTOFF")
            digest = row["training_observations_sha256"]
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("TRAINING_DIGEST")
            if type(row.get("training_games")) is not int or row["training_games"] <= 0:
                raise ValueError("TRAINING_COUNT")
            score = score_matrix(row["expected_home_goals"], row["expected_away_goals"])
            margin,total = marginal_scores(score)
            p = distribution_from_matrix(score, margin, total)
            # V4.1 rounds rates and truncates at eleven goals. Compare against
            # the same legacy truncation, not the expanded research matrix.
            h,a=row["expected_home_goals"],row["expected_away_goals"]
            hp=[math.exp(-h)*h**i/math.factorial(i) for i in range(12)]
            ap=[math.exp(-a)*a**i/math.factorial(i) for i in range(12)]
            z=sum(hp)*sum(ap)
            legacy=[0.,0.,0.]
            for i,x in enumerate(hp):
                for j,y in enumerate(ap):
                    legacy[0 if i>j else 1 if i==j else 2]+=x*y/z
            for key,expected in zip(("p_home","p_draw","p_away"),legacy):
                value=row[key]
                if type(value) not in (int,float) or not math.isfinite(value) or abs(value-expected)>2e-5:
                    raise ValueError("LEGACY_PROBABILITY_MISMATCH")
            out["rows"].append({"league":league,"event_id":event,
                "kickoff_utc":kick.isoformat(),"prediction_utc":pred.isoformat(),
                "training_observations_sha256":digest,
                "probabilities":p,"asian_scenarios":asian_scenarios(margin,total),
                "calibrated":False,"production_recommendations":"DISABLED"})
        except (ValueError, KeyError, TypeError, OverflowError):
            rejects["INVALID_OR_INELIGIBLE_ROW"] += 1
    out["rejected"]=dict(rejects)
    out["reason"]="UNCALIBRATED_RESEARCH_ONLY" if out["rows"] else "NO_ELIGIBLE_PREMATCH_ROWS"
    return out


def read_json(path):
    def unique(pairs):
        obj={}
        for key,value in pairs:
            if key in obj:
                raise ValueError("DUPLICATE_JSON_KEY")
            obj[key]=value
        return obj
    def reject(value):
        raise ValueError("NONFINITE_JSON")
    raw=Path(path).read_bytes()
    if len(raw)>16_000_000:
        raise ValueError("INPUT_TOO_LARGE")
    return json.loads(raw,object_pairs_hook=unique,parse_constant=reject)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--shadow",required=True)
    parser.add_argument("--collection",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    def load(path):
        try:
            return read_json(path)
        except (OSError,ValueError,TypeError,RecursionError):
            return None
    result=evaluate(load(args.shadow),load(args.collection),datetime.now(timezone.utc))
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix(target.suffix+".tmp")
    temp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+"\n",encoding="utf-8")
    temp.replace(target)
    print(json.dumps({"status":result["status"],"reason":result["reason"],"research_rows":len(result["rows"])}))


if __name__=="__main__":
    main()
