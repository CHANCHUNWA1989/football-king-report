"""REAL three-market 2026 separate-year OOS evidence, not market ROI.

Train the existing original-A role shrinkage/Poisson algorithm on ONLY 2025
genuine UEFA national-team score rows; predict all qualifying 2026 fixtures
(through Oct 6) and *then* compare to the withheld real full-time scores.

Reuses ops/asian_handicap_research and ops/all_market_scenarios quarter-line
settlement/distribution, not a second contradictory settlement engine.

All AH and totals *lines are predeclared hypothetical* and fixed for every
fixture: no actual bookmaker offer, historical tradable odds, original kickoff
timestamps, time-sealed model outputs, external data rights, positive EV, or
profit strategy. A rates model only — NOT Poisson/DC multi-market calibration.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path

from .asian_handicap_research import TYPES, grade as handicap_grade
from .all_market_scenarios import ah_scenario, total_scenario
from .live_uefa_nations_three_model_probe import _read_source, _parse
from .live_uefa_2026_holdout_test import (
    _original_a_real_rates, _original_a_real_formula,
    TRAIN_CUTOFF, TEST_START, TEST_END, MIN_TRAIN, MIN_TEST,
)
from .shadow_forecast import poisson_1x2
from .asian_handicap_research import split_lines

SCHEMA = "football-king-2026-three-market-real-date-split-v1"
CLASSES_1X2 = ("HOME", "DRAW", "AWAY")
# Ex ante example lines, not actual sportsbook handicap/totals.
MARKETS = (
    ("AH_HOME_-0.25", "AH", "HOME", -0.25),
    ("AH_AWAY_+0.25", "AH", "AWAY", 0.25),
    ("AH_HOME_-0.75", "AH", "HOME", -0.75),
    ("AH_AWAY_+0.75", "AH", "AWAY", 0.75),
    ("TOTAL_OVER_2.50", "TOTAL", "OVER", 2.5),
    ("TOTAL_UNDER_2.50", "TOTAL", "UNDER", 2.5),
    ("TOTAL_OVER_2.75", "TOTAL", "OVER", 2.75),
    ("TOTAL_UNDER_2.75", "TOTAL", "UNDER", 2.75),
)


def total_grade(home_goals, away_goals, side, line):
    """Exactly match the original all_market_scenarios.total_scenario split."""
    if (type(home_goals) is not int or type(away_goals) is not int
            or not 0 <= home_goals <= 25 or not 0 <= away_goals <= 25
            or side not in ("OVER", "UNDER")):
        raise ValueError("INVALID_REAL_TOTAL_MARKET_INPUT")
    left, right = split_lines(line)
    multiplier = 1 if side == "OVER" else -1
    combined = sum(
        1 if (home_goals+away_goals)*4*multiplier-quarter*multiplier > 0
        else -1 if (home_goals+away_goals)*4*multiplier-quarter*multiplier < 0
        else 0
        for quarter in (left, right)
    )
    return {2:"FULL_WIN",1:"HALF_WIN",0:"PUSH",
            -1:"HALF_LOSS",-2:"FULL_LOSS"}[combined]


def _direction(score):
    a,b=score
    return "HOME" if a>b else "DRAW" if a==b else "AWAY"


def _distribution(home_rate,away_rate,market):
    label, kind, side, line=market
    s=(ah_scenario(home_rate,away_rate,side,line)
       if kind=="AH" else total_scenario(home_rate,away_rate,side=side,line=line))
    dist=s["settlement_probabilities"]
    if (type(dist) is not dict or set(dist)!=set(TYPES)
            or any(type(x) not in (float,int) or
                   not math.isfinite(x) or x<0 or x>1
                   for x in dist.values())
            or abs(sum(dist.values())-1)>1e-5):
        raise ValueError("INVALID_EXISTING_MARKET_DISTRIBUTION")
    return dist


def _actual_grade(row,market):
    gh,ga=row["score_ft"]
    _,kind,side,line=market
    return (handicap_grade(gh,ga,side,line)
            if kind=="AH" else total_grade(gh,ga,side,line))


def _score(dist,observed,classes):
    if set(dist)!=set(classes) or observed not in classes:
        raise ValueError("INVALID_PAIRED_MODEL_OUTCOME")
    return (
        sum((dist[k]-(1 if k==observed else 0))**2 for k in classes),
        -math.log(max(dist[observed],1e-15))
    )


def _summarize(class_order,observed,forecasts,baseline):
    if len(observed)!=len(forecasts) or not observed:
        raise ValueError("INCOMPLETE_FIXED_COHORT")
    observed_counts=Counter(observed)
    brier,logloss,baseline_brier,baseline_logloss=0,0,0,0
    for outcome,p in zip(observed,forecasts):
        b,l=_score(p,outcome,class_order)
        bb,ll=_score(baseline,outcome,class_order)
        brier+=b;logloss+=l
        baseline_brier+=bb;baseline_logloss+=ll
    n=len(observed)
    return {
        "heldout_real_matches":n,
        "actual_class_counts":{k:observed_counts[k] for k in class_order},
        "model_mean_multiclass_brier":round(brier/n,6),
        "model_mean_logloss":round(logloss/n,6),
        "training_only_unconditional_baseline_mean_brier":round(baseline_brier/n,6),
        "training_only_unconditional_baseline_mean_logloss":round(baseline_logloss/n,6),
        "model_brier_better_than_predefined_baseline":brier<baseline_brier,
        "model_logloss_better_than_predefined_baseline":logloss<baseline_logloss,
    }


def _baseline(rows,kind,market=None):
    classes=CLASSES_1X2 if kind=="1X2" else TYPES
    observed=[_direction(r["score_ft"]) if kind=="1X2"
              else _actual_grade(r,market) for r in rows]
    n=len(observed);c=Counter(observed)
    # Jeffreys smoothing; prevents a category absent in 2025 from
    # producing infinite 2026 logloss. Never fitted to 2026 labels.
    return {k:(c[k]+.5)/(n+.5*len(classes)) for k in classes}


def evaluate(train,test):
    if (type(train) is not list or type(test) is not list or
            len(train)<MIN_TRAIN or len(test)<MIN_TEST
            or not all(type(r) is dict and r["date"]<=TRAIN_CUTOFF for r in train)
            or not all(type(r) is dict and TEST_START<=r["date"]<=TEST_END for r in test)):
        raise ValueError("INVALID_SEPARATE_YEAR_COHORT")
    appearances=Counter()
    for row in train:
        appearances[row["home"]]+=1
        appearances[row["away"]]+=1
    qualifying=[r for r in test
                if appearances[r["home"]]>=5 and appearances[r["away"]]>=5]
    if len(qualifying)<MIN_TEST:
        raise ValueError("INSUFFICIENT_PRESPECIFIED_TEAM_COVERAGE")
    # A 1X2, two directions of AH, two directions of OU, all on
    # exactly SAME 186 held-out match identities.
    labels={"1X2":[]}
    forecasts={"1X2":[]}
    for name,*_ in MARKETS:
        labels[name]=[];forecasts[name]=[]
    for row in qualifying:
        h,a=row["home"],row["away"]
        hg,ag=_original_a_real_rates(train,h,a)
        p3=poisson_1x2(hg,ag)
        # Explicitly prove this is the unchanged original A 1X2 model.
        same=_original_a_real_formula(train,h,a)
        if max(abs(x-y) for x,y in zip(p3,same))>1e-8:
            raise ValueError("ORIGINAL_A_THREE_MARKET_RATE_DRIFT")
        forecasts["1X2"].append(dict(zip(CLASSES_1X2,p3)))
        labels["1X2"].append(_direction(row["score_ft"]))
        for market in MARKETS:
            name=market[0]
            forecasts[name].append(_distribution(hg,ag,market))
            labels[name].append(_actual_grade(row,market))
    n=len(qualifying)
    results={
        "1X2":_summarize(CLASSES_1X2,labels["1X2"],
                        forecasts["1X2"],_baseline(train,"1X2")),
    }
    for market in MARKETS:
        name=market[0]
        results[name]=_summarize(TYPES,labels[name],forecasts[name],
                                _baseline(train,"AH_OR_OU",market))
        results[name]["market_type"]=market[1]
        results[name]["side"]=market[2]
        results[name]["fixed_hypothetical_line_not_observed_quote"]=market[3]
    return {
        "training_real_matches":len(train),
        "all_2026_test_rows":len(test),
        "paired_heldout_match_count":n,
        "excluded_predeclared_insufficient_2025_team_history":len(test)-n,
        "results":results,
        "source_team_identity_native_uefa_ids_verified":False,
        "model_only_original_a_role_poisson_not_challenger_ah_ou":True,
        "no_lookahead_2026_scores_used_for_training":True,
    }


def audit(*,source_reader=_read_source):
    try:
        raw=source_reader()
        rows,last=_parse(raw)
        train=[r for r in rows if r["date"]<=TRAIN_CUTOFF]
        test=[r for r in rows if r["date"]>=TEST_START]
        result=evaluate(train,test)
        return {
            "schema":SCHEMA,
            "status":"HOLD",
            "reason":"TRUE_UNSEEN_DATE_SPLIT_THREE_MARKET_SCORES_BUT_NO_REAL_MARKET_PRICE",
            "source_sha256_unattested":hashlib.sha256(raw).hexdigest(),
            "actual_source_results_latest":last.isoformat(),
            "historical_kickoff_time_or_source_publication_verified":False,
            "actual_offered_asian_lines_and_prices_collected":False,
            "actual_offered_total_lines_and_prices_collected":False,
            "historical_market_roi_or_ev_verified":False,
            "model_line_probability_independently_calibrated":False,
            "certified_prospective_three_market_samples":0,
            "positive_ev_verified":False,
            "production_recommendations":"DISABLED",
            **result,
        }
    except Exception as exc:
        return {
            "schema":SCHEMA,"status":"HOLD",
            "reason":"TRUE_REAL_THREE_MARKET_HOLDOUT_UNAVAILABLE",
            "safe_failure_type":type(exc).__name__,
            "positive_ev_verified":False,
            "production_recommendations":"DISABLED",
            "certified_prospective_three_market_samples":0,
        }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True)
    args=p.parse_args(argv)
    report=audit()
    target=Path(args.output)
    if target.exists() or target.is_symlink():
        raise ValueError("REFUSE_TO_OVERWRITE_REAL_THREE_MARKET_AUDIT")
    blob=(json.dumps(report,sort_keys=True,ensure_ascii=False,
                     separators=(",",":"),allow_nan=False)+"\n").encode()
    fd=os.open(target,os.O_CREAT|os.O_EXCL|os.O_WRONLY|
               getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as writer:
        writer.write(blob);writer.flush();os.fsync(writer.fileno())
    print("REAL_2026_THREE_MARKET_OOS",blob.decode().strip())
    return 0 if report.get("paired_heldout_match_count")==186 else 1


if __name__=="__main__":
    raise SystemExit(main())
