"""Private historical halftime-state study; not market handicap calibration.

The historical source snapshot postdates the matches. A chronological holdout
is a retrospective split, not an independently witnessed prospective forecast.
Shot xG is a provider statistic, not a causal estimate of tactical intensity.
"""
import math
from datetime import date
from deep_handicap_historical_inputs import _decode, _id, parse_event_structure, MAX_BYTES

SCHEMA="football-king-dhe-halftime-historical-v1"
SPLIT=date(2022,11,29)
START=date(2022,11,20)
END=date(2022,12,2)


def extract(raw,match):
    """Replay regulation goals and shot xG by half, reconcile indexed FT."""
    mid=_id(match["match_id"])
    h=_id(match["home_team"]["home_team_id"])
    a=_id(match["away_team"]["away_team_id"])
    if match["competition_stage"]["name"]!="Group Stage" or match["match_status"]!="available":
        raise ValueError("WRONG_MATCH_SCOPE")
    day=date.fromisoformat(match["match_date"])
    if not START<=day<=END:
        raise ValueError("WRONG_MATCH_DATE")
    _, features=parse_event_structure(raw,mid,h,a)
    events=_decode(raw,MAX_BYTES)
    goals={h:[0,0],a:[0,0]}
    xg={h:[[],[]],a:[[],[]]}
    for event in events:
        period=event["period"]
        if period not in (1,2):
            if period in (3,4,5):
                raise ValueError("NON_REGULATION_GROUP_STAGE")
            continue
        kind=event["type"]["name"]
        if kind not in ("Shot","Own Goal For"):
            continue
        team=_id(event["team"]["id"])
        if team not in goals:
            raise ValueError("GOAL_TEAM_MISMATCH")
        if kind=="Own Goal For":
            goals[team][period-1]+=1
            continue
        shot=event["shot"]
        outcome=shot["outcome"]["name"]
        if type(outcome) is not str or not outcome:
            raise ValueError("MISSING_SHOT_OUTCOME")
        goals[team][period-1]+=int(outcome=="Goal")
        xg[team][period-1].append(shot["statsbomb_xg"])
    for team,key,side in ((h,"home_score","home"),(a,"away_score","away")):
        if type(match[key]) is not int or sum(goals[team])!=match[key]:
            raise ValueError("REGULATION_SCORE_RECONCILIATION_FAILED")
        if abs(math.fsum(xg[team][0]+xg[team][1])-features[side+"_shot_xg"])>1e-9:
            raise ValueError("SHOT_XG_RECONCILIATION_FAILED")
    return {"match_id":mid,"day":day.isoformat(),"home_ht":goals[h][0],"away_ht":goals[a][0],
            "home_first_xg":math.fsum(xg[h][0]),"home_second_xg":math.fsum(xg[h][1]),
            "away_first_xg":math.fsum(xg[a][0]),"away_second_xg":math.fsum(xg[a][1])}


def evaluate(rows):
    """Fit a descriptive multiplier on early matches; assess once on late matches.

    A leading team's first-half shot xG is used as an intentionally simple
    reference, not a validated forecast. Fitted ratio uses pooled sums, not
    a mean of unstable per-match ratios. No deployment or threshold search.
    """
    out={"schema":SCHEMA,"status":"HOLD","production_recommendations":"DISABLED",
         "true_forward_sample_count":0,"model_accuracy_verified":False,
         "causal_tactical_effect_verified":False,"actual_handicap_lines_available":False,
         "private_metrics":None,"fit_performed":False}
    if type(rows) is not list or len(rows)!=48:
        return {**out,"reason":"INCOMPLETE_PREDECLARED_GROUP_STAGE"}
    try:
        seen=set()
        groups={"train":[],"holdout":[]}
        counts={"train":0,"holdout":0}
        for row in rows:
            mid=_id(row["match_id"])
            if mid in seen:
                raise ValueError("DUPLICATE_MATCH")
            seen.add(mid)
            day=date.fromisoformat(row["day"])
            if not START<=day<=END:
                raise ValueError("BAD_DATE")
            group="train" if day<SPLIT else "holdout"
            counts[group]+=1
            h,a=row["home_ht"],row["away_ht"]
            if any(type(x) is not int or not 0<=x<=25 for x in (h,a)):
                raise ValueError("BAD_HALF_SCORE")
            vals=[row[side+"_"+half+"_xg"] for side in ("home","away") for half in ("first","second")]
            if any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=50 for x in vals):
                raise ValueError("BAD_HALF_XG")
            if abs(h-a)>=2:
                side="home" if h>a else "away"
                groups[group].append((row[side+"_first_xg"],row[side+"_second_xg"]))
        if counts!={"train":32,"holdout":16}:
            raise ValueError("SPLIT_COUNT_MISMATCH")
        n={k:len(v) for k,v in groups.items()}
        out.update(match_counts=counts,eligible_halftime_leader_counts=n)
        # Conservative pilot minimum; not an inferential sample-size guarantee.
        train,test=groups["train"],groups["holdout"]
        denom=math.fsum(x for x,y in train)
        if len(train)<10 or len(test)<5 or denom<=0:
            return {**out,"reason":"INSUFFICIENT_HALFTIME_LEADER_SAMPLE"}
        ratio=math.fsum(y for x,y in train)/denom
        if not math.isfinite(ratio):
            raise ValueError("INVALID_RATIO")
        def mse(factor):
            return math.fsum((factor*x-y)**2 for x,y in test)/len(test)
        out.update(fit_performed=True,reason="RETROSPECTIVE_DESCRIPTIVE_ONLY",
                   private_metrics={"train_pooled_ratio":ratio,"holdout_mse_fitted":mse(ratio),
                                    "holdout_mse_fixed_085":mse(.85),"holdout_mse_fixed_1":mse(1.0)})
        return out
    except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
        return {**out,"reason":"INVALID_HISTORICAL_COHORT","private_metrics":None,"fit_performed":False}
