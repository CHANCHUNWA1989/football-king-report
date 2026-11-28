"""Fixed opponent-adjusted, time-decayed Poisson research challenger.

No parameter selection on assessment results, odds, xG claims or production
promotion. Historical replay is date-only and not authentic forward evidence.
"""
import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .shadow_forecast import poisson_1x2, predict_league
except ImportError:
    from shadow_forecast import poisson_1x2, predict_league

MODEL = "opponent-adjusted-decay90-shrink8-v1"
HALF_LIFE = 90
PRIOR = 8
ITERATIONS = 12
HK = ZoneInfo("Asia/Hong_Kong")
LEAGUES = ("epl","championship","bundesliga","laliga","seriea","ligue1")


def history_before(records, league, day):
    """Normalize only finished earlier-day results, reject conflicting revisions."""
    unique = {}
    for r in records:
        if not isinstance(r,dict) or r.get("league") != league or r.get("status") != "FINISHED":
            continue
        try:
            d = date.fromisoformat(r["date"])
            h,a = r["home"],r["away"]
            score = r["score_ft"]
            if d >= day or not all(isinstance(t,str) and 0<len(t)<110 for t in (h,a)) or h==a:
                continue
            if not isinstance(score,list) or len(score)!=2 or not all(type(v) is int and 0<=v<=20 for v in score):
                continue
        except (KeyError,TypeError,ValueError):
            continue
        key=(d,h,a)
        value=tuple(score)
        if key in unique and unique[key]!=value:
            raise ValueError("CONFLICTING_HISTORY")
        unique[key]=value
    return [(d,h,a,*s) for (d,h,a),s in sorted(unique.items())]


def fit(history, day):
    """Regularized weighted observed/expected updates; pooled venue strength."""
    if len(history)<30 or any(d>=day for d,*_ in history):
        return None
    weights=[2**(-(day-r[0]).days/HALF_LIFE) for r in history]
    mass=math.fsum(weights)
    if mass<15:
        return None
    home=max(.3,math.fsum(w*r[3] for w,r in zip(weights,history))/mass)
    away=max(.3,math.fsum(w*r[4] for w,r in zip(weights,history))/mass)
    apps=Counter(t for _,h,a,_,_ in history for t in (h,a))
    attack=dict.fromkeys(apps,1.0)
    defense=dict.fromkeys(apps,1.0)
    for _ in range(ITERATIONS):
        ao=Counter(); ae=Counter(); do=Counter(); de=Counter()
        for w,(_,h,a,gh,ga) in zip(weights,history):
            ao[h]+=w*gh; ae[h]+=w*home*defense[a]
            ao[a]+=w*ga; ae[a]+=w*away*defense[h]
            do[h]+=w*ga; de[h]+=w*away*attack[a]
            do[a]+=w*gh; de[a]+=w*home*attack[h]
        # Prior contributes eight neutral goal-exposure units, not eight matches.
        # Simultaneous damped updates avoid an unstable feedback loop.
        attack={t:.5*attack[t]+.5*min(3,max(.25,(ao[t]+PRIOR)/(ae[t]+PRIOR))) for t in apps}
        defense={t:.5*defense[t]+.5*min(3,max(.25,(do[t]+PRIOR)/(de[t]+PRIOR))) for t in apps}
    return home,away,attack,defense,apps


def rates(fitted,h,a):
    if fitted is None:
        return None
    home,away,attack,defense,apps=fitted
    if apps[h]<3 or apps[a]<3 or h==a:
        return None
    return (min(5.5,max(.1,home*attack[h]*defense[a])),
            min(5.5,max(.1,away*attack[a]*defense[h])))


def metrics(rows,key):
    if not rows:
        return None
    n=len(rows)
    return {"n":n,"hits":sum(max(range(3),key=lambda i:r[key][i])==r["y"] for r in rows),
        "log_loss":math.fsum(-math.log(max(r[key][r["y"]],1e-12)) for r in rows)/n,
        "brier":math.fsum(sum((p-int(i==r["y"]))**2 for i,p in enumerate(r[key])) for r in rows)/n,
        "mean_draw_probability":math.fsum(r[key][1] for r in rows)/n,
        "actual_draw_fraction":sum(r["y"]==1 for r in rows)/n}


def replay(records,league):
    """Paired daily walk-forward replay on identical cases; no same-day labels."""
    normalized=history_before(records,league,date.max)
    groups=defaultdict(list)
    for r in normalized:
        groups[r[0]].append(r)
    earlier=[]; result=[]
    for day,today in sorted(groups.items()):
        model=fit(earlier,day)
        if model is not None:
            cutoff=datetime.combine(day,datetime.min.time(),tzinfo=HK).astimezone(timezone.utc)
            training=[{"date":d.isoformat(),"home":h,"away":a,"score_ft":[gh,ga],
                        "status":"FINISHED"} for d,h,a,gh,ga in earlier]
            future=[{"date":day.isoformat(),"home":h,"away":a,"status":"SCHEDULED",
                     "event_id":str(i),"kickoff_utc":(cutoff+timedelta(hours=23)).isoformat()}
                    for i,(_,h,a,_,_) in enumerate(today)]
            base=predict_league(training+future,league,cutoff)
            for p in base:
                _,h,a,gh,ga=today[int(p["event_id"])]
                r=rates(model,h,a)
                if r is None:
                    continue
                result.append({"date":day.isoformat(),"league":league,
                    "y":0 if gh>ga else 1 if gh==ga else 2,
                    "original":[p["p_home"],p["p_draw"],p["p_away"]],
                    "candidate":list(poisson_1x2(*r)),
                    "training_games":len(earlier)})
        earlier.extend(today)
    return result


def build(shadow,finished,now):
    out={"schema":"football-king-opponent-adjusted-research-v1","model":MODEL,
         "status":"HOLD","production_recommendations":"DISABLED","research_only":True,
         "automatic_model_promotion":False,"independently_verified":False,
         "positive_ev_verified":False,"recommendation_count":0,"predictions":[],
         "parameters":{"half_life_days":HALF_LIFE,"prior_goal_exposure":PRIOR,"iterations":ITERATIONS},
         "retrospective":{},"generated_utc":now.isoformat()}
    try:
        if (shadow.get("schema")!="football-king-uncalibrated-shadow-1"
            or shadow.get("status")!="SHADOW_ONLY" or shadow.get("production_recommendations")!="DISABLED"
            or finished.get("schema")!="football-king-single-source-finished-results-1"
            or finished.get("production_recommendations")!="DISABLED"
            or finished["captured_utc"]!=shadow["as_of_utc"]):
            return out
        captured=datetime.fromisoformat(shadow["as_of_utc"])
        if captured.tzinfo is None or not timedelta(0)<=now-captured<=timedelta(minutes=30):
            return out
        records=finished["records"]
        preds=shadow["predictions"]
        if not isinstance(records,list) or len(records)>10000 or not isinstance(preds,list) or len(preds)>3000:
            return out
        if type(shadow.get("predictions_count")) is not int or shadow["predictions_count"]!=len(preds):
            return out
    except (AttributeError,KeyError,ValueError,TypeError,OverflowError):
        return out
    day=captured.astimezone(HK).date()
    counts=Counter((p.get("league"),p.get("event_id")) for p in preds
                   if isinstance(p,dict) and isinstance(p.get("league"),str) and isinstance(p.get("event_id"),str))
    for league in LEAGUES:
        try:
            history=history_before(records,league,day)
            fitted=fit(history,day)
            digest=hashlib.sha256(json.dumps([(d.isoformat(),h,a,gh,ga) for d,h,a,gh,ga in history],
                ensure_ascii=False,default=str).encode()).hexdigest()
            for p in preds:
                if not isinstance(p,dict) or p.get("league")!=league:
                    continue
                try:
                    if (not isinstance(p.get("event_id"),str) or counts[(league,p["event_id"])]!=1
                        or p.get("model")!="poisson-shrinkage-unvalidated-v4.1"
                        or p.get("calibrated") is not False or p.get("production_recommendations")!="DISABLED"
                        or date.fromisoformat(p["training_cutoff_local_day"])>=day
                        or datetime.fromisoformat(p["prediction_utc"])>captured
                        or datetime.fromisoformat(p["kickoff_utc"])<=now+timedelta(minutes=10)):
                        continue
                    r=rates(fitted,p["home"],p["away"])
                    if r is None:
                        continue
                    out["predictions"].append({"league":league,"event_id":p["event_id"],
                        "kickoff_utc":p["kickoff_utc"],"training_games":len(history),
                        "training_sha256":digest,"expected_home_goals":r[0],"expected_away_goals":r[1],
                        "p":list(poisson_1x2(*r)),"original":[p["p_home"],p["p_draw"],p["p_away"]],
                        "production_recommendations":"DISABLED"})
                except (KeyError,ValueError,TypeError,OverflowError):
                    continue
            rows=replay([r for r in records if isinstance(r,dict) and r.get("league")==league
                and isinstance(r.get("date"),str) and r["date"]<day.isoformat()],league)
            out["retrospective"][league]={"original":metrics(rows,"original"),
                "candidate":metrics(rows,"candidate"),"date_only_not_forward_evidence":True}
        except (ValueError,TypeError,OverflowError):
            out["retrospective"][league]={"status":"HOLD","reason":"INVALID_OR_CONFLICTING_HISTORY"}
    return out


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shadow",required=True);p.add_argument("--finished",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    def load(path):
        try:
            f=Path(path)
            if f.stat().st_size>12_000_000:
                return {}
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError,ValueError):
            return {}
    result=build(load(a.shadow),load(a.finished),datetime.now(timezone.utc))
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"model":MODEL,"research_predictions":len(result["predictions"]),
        "retrospective":result["retrospective"],"production_recommendations":"DISABLED"},ensure_ascii=False))


if __name__=="__main__":
    main()
