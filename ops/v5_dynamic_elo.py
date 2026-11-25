"""V5 phase 2: fixed, untuned Elo/recency goal-rate research challenger.

Date-only retrospective archive adapter, not authenticated pre-match evidence.
Exact source team labels are local to each archive, not cross-league identities.
No executable odds, current fixture forecasts, or automatic promotion.
"""
import argparse
from collections import defaultdict, Counter
from datetime import date
import hashlib
import json
import math
from pathlib import Path

MODEL_ID = "v5-fixed-elo-recency-goals-v1"
K = 20
HOME_ELO = 55
HALF_LIFE_DAYS = 120
PRIOR = 6
ELO_BLEND = .5
MIN_HISTORY = 30
MIN_TEAM = 3
MAX_ROWS = 650

def parse_archive(doc, *, historical=False):
    if type(historical) is not bool:
        raise ValueError("INVALID_HISTORY_MODE")
    if not isinstance(doc, dict) or not isinstance(doc.get("matches"), list):
        raise ValueError("INVALID_ARCHIVE")
    if len(doc["matches"]) > MAX_ROWS:
        raise ValueError("ARCHIVE_LIMIT")
    rows, seen = [], set()
    for r in doc["matches"]:
        if not isinstance(r, dict):
            raise ValueError("INVALID_MATCH")
        h, a = r.get("team1"), r.get("team2")
        if not all(isinstance(x, str) and 0 < len(x.strip()) < 110 for x in (h,a)) or h == a:
            raise ValueError("INVALID_TEAM")
        d = date.fromisoformat(r["date"])
        if not (2021 if historical else 2023) <= d.year <= 2026:
            raise ValueError("INVALID_DATE")
        key = (d,h,a)
        if key in seen:
            raise ValueError("DUPLICATE_OR_CONFLICTING_MATCH")
        seen.add(key)
        score = r.get("score")
        score = score.get("ft") if isinstance(score,dict) else score
        if not isinstance(score,list) or len(score)!=2 or not all(type(v) is int and 0<=v<=20 for v in score):
            raise ValueError("INVALID_FINISHED_SCORE")
        rows.append((d,h,a,*score))
    return sorted(rows)

def probabilities(h,a):
    if not all(math.isfinite(v) and .1 <= v <= 5.5 for v in (h,a)):
        raise ValueError("INVALID_RATE")
    x = [math.exp(-h)*h**i/math.factorial(i) for i in range(12)]
    y = [math.exp(-a)*a**i/math.factorial(i) for i in range(12)]
    p = [0.,0.,0.]
    for i, v in enumerate(x):
        for j, w in enumerate(y):
            p[0 if i>j else 1 if i==j else 2] += v*w
    return [v/sum(p) for v in p]

def rates(history, day, home, away, ratings, weighted):
    # The caller supplies only days strictly before day.
    if any(r[0]>=day for r in history):
        raise ValueError("NON_PRIOR_HISTORY")
    if len(history)<MIN_HISTORY:
        return None
    appearances = Counter(t for _,h,a,_,_ in history for t in (h,a))
    if min(appearances[home],appearances[away])<MIN_TEAM:
        return None
    w = [2**(-(day-d).days/HALF_LIFE_DAYS) if weighted else 1. for d,*_ in history]
    lh = max(.3,sum(v*r[3] for v,r in zip(w,history))/sum(w))
    la = max(.3,sum(v*r[4] for v,r in zip(w,history))/sum(w))
    def role(team, position, goals, prior):
        pairs = [(v,r[goals]) for v,r in zip(w,history) if r[position]==team]
        return (sum(v*g for v,g in pairs)+PRIOR*prior)/(sum(v for v,_ in pairs)+PRIOR)
    h = role(home,1,3,lh)*role(away,2,3,lh)/lh
    a = role(away,2,4,la)*role(home,1,4,la)/la
    if weighted:
        delta = ratings.get(home,1500.)-ratings.get(away,1500.)
        # League venue averages already contain home advantage; no double count.
        factor = 10**(max(-600.,min(600.,delta))/1600.)
        h = h**(1-ELO_BLEND)*(lh*factor)**ELO_BLEND
        a = a**(1-ELO_BLEND)*(la/factor)**ELO_BLEND
    return tuple(max(.1,min(5.5,v)) for v in (h,a))

def score(p,y):
    return (-math.log(max(p[y],1e-15)),sum((v-int(i==y))**2 for i,v in enumerate(p)),
            int(max(range(3),key=lambda i:p[i])==y))

def replay(doc, *, historical=False):
    rows = parse_archive(doc, historical=historical)
    groups = defaultdict(list)
    for r in rows:
        groups[r[0]].append(r)
    earlier, ratings, cases = [], {}, []
    for day in sorted(groups):
        batch = groups[day]
        changes = defaultdict(float)
        for _,h,a,gh,ga in batch:
            base = rates(earlier,day,h,a,ratings,False)
            cand = rates(earlier,day,h,a,ratings,True)
            if base is not None and cand is not None:
                y = 0 if gh>ga else 1 if gh==ga else 2
                cases.append({"date":day.isoformat(),"home":h,"away":a,"y":y,
                              "baseline":probabilities(*base),"candidate":probabilities(*cand)})
            expected = 1/(1+10**((ratings.get(a,1500.)-ratings.get(h,1500.)-HOME_ELO)/400))
            observed = 1 if gh>ga else .5 if gh==ga else 0
            delta = K*(observed-expected)
            changes[h]+=delta
            changes[a]-=delta
        # No within-day outcomes used for any same-day prediction.
        for team,delta in changes.items():
            ratings[team]=ratings.get(team,1500.)+delta
        earlier.extend(batch)
    return cases

def summarize(cases):
    if not cases:
        return None
    out={}
    for name in ("baseline","candidate"):
        vals=[score(r[name],r["y"]) for r in cases]
        n=len(vals)
        out[name]={"n":n,"log_loss":sum(v[0] for v in vals)/n,
                   "brier":sum(v[1] for v in vals)/n,"correct":sum(v[2] for v in vals),
                   "home_top_count":sum(max(range(3),key=lambda i:r[name][i])==0 for r in cases)}
    out["actual_home_count"]=sum(r["y"]==0 for r in cases)
    return out

def build(doc):
    cases=replay(doc)
    return {"schema":"football-king-v5-elo-replay-v1","model_id":MODEL_ID,
            "status":"RESEARCH_ONLY" if cases else "HOLD",
            "archive_sha256":hashlib.sha256(json.dumps(doc,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest(),
            "parameters":{"k":K,"home_elo":HOME_ELO,"half_life_days":HALF_LIFE_DAYS,"prior":PRIOR,"elo_blend":ELO_BLEND},
            "metrics":summarize(cases),"cases":cases,
            "prior_days_only":True,"same_day_update_after_all_predictions":True,
            "source_results_independently_verified":False,"assessment_previously_inspected":True,
            "prospective_validation":False,"market_comparison_available":False,
            "cross_league_strength_calibrated":False,"automatic_promotion":False,
            "production_recommendations":"DISABLED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--archive",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    source=Path(args.archive)
    if source.stat().st_size>500000:
        raise ValueError("ARCHIVE_BYTES_LIMIT")
    result=build(json.loads(source.read_text(encoding="utf-8")))
    Path(args.output).write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="cases"},allow_nan=False))
if __name__=="__main__":
    main()
