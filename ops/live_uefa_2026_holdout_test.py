"""Real independent 2026 national-team holdout, no synthetic match outcomes.

Train ONLY on full UEFA-vs-UEFA internationals dated 2025, withhold EVERY
2026 match through 2026-10-06. All 2026 final scores are read exclusively
for evaluation, never training. Exact 2026-10-31 pinned public CSV bytes
checked by Git blob SHA1. Source contains only dates, not actual pre-kickoff
timestamps; this is a retrospective DATE-SPLIT evaluation, not third-party
witnessed pre-match capture or market EV calibration.

Original A formula is replicated exactly from ops.shadow_forecast.predict_league
using poisson_1x2 and its six-game home/away smoothing; it is NOT a native
international model and this does NOT pretend original A emitted forecasts
in 2025. The two other model classes are ACTUAL Penaltyblog 1.13.1.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

from .shadow_forecast import poisson_1x2
from .live_uefa_nations_three_model_probe import (
    _read_source, _parse, _vector, _status,
)

SCHEMA = "football-king-2026-real-international-date-split-holdout-v1"
TRAIN_CUTOFF = "2025-12-31"
TEST_START = "2026-01-01"
TEST_END = "2026-10-06"
MIN_TRAIN = 200
MIN_TEST = 150


def _original_a_real_rates(training, home, away):
    """Exact old A role-shrinkage goal rates; 2025-only for date-split OOS."""
    prior = 6
    seen = defaultdict(int)
    home_for = defaultdict(list)
    away_for = defaultdict(list)
    for r in training:
        h, a = r["home"], r["away"]
        gh, ga = r["score_ft"]
        seen[h] += 1
        seen[a] += 1
        home_for[h].append((gh, ga))
        away_for[a].append((ga, gh))
    if seen[home] < 3 or seen[away] < 3:
        raise ValueError("INSUFFICIENT_A_TRAINING_TEAM_APPEARANCES")
    league_home = max(0.3, sum(r["score_ft"][0] for r in training)/len(training))
    league_away = max(0.3, sum(r["score_ft"][1] for r in training)/len(training))
    def role(team, samples, which, baseline):
        obs = samples[team]
        return (sum(r[which] for r in obs) + prior*baseline)/(len(obs)+prior)
    h_attack = role(home, home_for, 0, league_home)
    a_defence = role(away, away_for, 1, league_home)
    a_attack = role(away, away_for, 0, league_away)
    h_defence = role(home, home_for, 1, league_away)
    expected_home = min(5.5,max(0.1,h_attack*a_defence/league_home))
    expected_away = min(5.5,max(0.1,a_attack*h_defence/league_away))
    return expected_home, expected_away

def _original_a_real_formula(training, home, away):
    """Same 1X2 formula as before; now shares exact rates with market replay."""
    expected_home, expected_away = _original_a_real_rates(training, home, away)
    return _vector(poisson_1x2(expected_home, expected_away))

def _loss(prob, outcome):
    if type(outcome) is not int or outcome not in (0,1,2):
        raise ValueError("INVALID_REAL_SCORE_RESULT")
    p = _vector(prob)
    y = [int(i==outcome) for i in range(3)]
    return {
        "brier_sum_0_to_2": sum((p[i]-y[i])**2 for i in range(3)),
        "log_loss": -math.log(max(1e-15,p[outcome])),
        "correct_direction": int(max(range(3),key=lambda i:p[i])==outcome),
        "predicted_max_confidence": max(p),
    }


def _summarize(values):
    n = len(values)
    if n == 0:
        raise ValueError("NO_VALID_HELDOUT_SCORES")
    return {
        "heldout_matches": n,
        "one_x_two_top_probability_accuracy": round(
            sum(x["correct_direction"] for x in values)/n, 6),
        "multiclass_brier_sum_0_to_2": round(
            sum(x["brier_sum_0_to_2"] for x in values)/n, 6),
        "mean_negative_log_likelihood": round(
            sum(x["log_loss"] for x in values)/n, 6),
        "over_70pct_confidence_count": sum(
            x["predicted_max_confidence"] >= 0.7 for x in values),
        "over_70pct_confidence_real_hit_count": sum(
            x["correct_direction"] for x in values
            if x["predicted_max_confidence"] >= 0.7),
    }


def evaluate(training, heldout, *, model_module):
    if (len(training) < MIN_TRAIN or len(heldout) < MIN_TEST
            or not all(r["date"] <= TRAIN_CUTOFF for r in training)
            or not all(TEST_START <= r["date"] <= TEST_END for r in heldout)
            or any(r["date"] < training[-1]["date"] for r in heldout)):
        raise ValueError("TRAIN_HOLDOUT_SPLIT_OR_COVERAGE_INVALID")
    counts = defaultdict(int)
    for r in training:
        counts[r["home"]] += 1
        counts[r["away"]] += 1
    # Pre-declared coverage excludes targets whose sides have <5 prior
    # training appearances. All 2026 target outcomes are retained for later
    # diagnostic and cohort coverage; never pick only successful predictions.
    qualifying = [r for r in heldout if
                  counts[r["home"]] >= 5 and counts[r["away"]] >= 5]
    if len(qualifying) < MIN_TEST:
        raise ValueError("REAL_HELDOUT_COHORT_TOO_SMALL")
    models = {
        "poisson": model_module.PoissonGoalsModel,
        "dixon_coles": model_module.DixonColesGoalModel,
    }
    scores = {k:[] for k in ("a_formula","poisson","dixon_coles","2025_frequency_baseline")}
    result_totals = [
        sum(1 for r in training if (
            0 if r["score_ft"][0] > r["score_ft"][1] else
            1 if r["score_ft"][0] == r["score_ft"][1] else 2) == outcome)
        for outcome in range(3)
    ]
    prior = [x/len(training) for x in result_totals]
    fitted = {}
    for key, klass in models.items():
        m = klass([r["score_ft"][0] for r in training],
                  [r["score_ft"][1] for r in training],
                  [r["home"] for r in training],
                  [r["away"] for r in training])
        m.fit()
        fitted[key] = m

    per_class = {name:{k:[] for k in ("home","draw","away")}
                 for name in scores}
    for row in qualifying:
        h, a = row["home"],row["away"]
        gh, ga = row["score_ft"]
        result = 0 if gh>ga else 1 if gh==ga else 2
        p = {
            "a_formula": _original_a_real_formula(training,h,a),
            "2025_frequency_baseline": prior,
            **{name:_vector(model.predict(h,a,max_goals=15,normalize=True).home_draw_away)
               for name, model in fitted.items()},
        }
        for name, v in p.items():
            scores[name].append(_loss(v,result))
            per_class[name][("home","draw","away")[result]].append(
                _loss(v,result))
    total = len(qualifying)
    stat = {name:_summarize(values) for name,values in scores.items()}
    for name in stat:
        stat[name]["real_2026_outcomes_home_draw_away"] = [
            len(per_class[name][cl]) for cl in ("home","draw","away")]
        n_hi=stat[name]["over_70pct_confidence_count"]
        stat[name]["over_70pct_confidence_observed_accuracy"] = (
            round(stat[name]["over_70pct_confidence_real_hit_count"]/n_hi,6)
            if n_hi else None)
        stat[name]["brier_better_than_2025_frequency_baseline"] = (
            stat[name]["multiclass_brier_sum_0_to_2"] <
            stat["2025_frequency_baseline"]["multiclass_brier_sum_0_to_2"])
        stat[name]["logloss_better_than_2025_frequency_baseline"] = (
            stat[name]["mean_negative_log_likelihood"] <
            stat["2025_frequency_baseline"]["mean_negative_log_likelihood"])
    return {
        "training_real_matches":len(training),
        "total_real_2026_result_rows":len(heldout),
        "evaluated_real_2026_matches":total,
        "excluded_due_to_less_than_five_2025_training_appearances":len(heldout)-total,
        "test_score_counts":stat["poisson"]["real_2026_outcomes_home_draw_away"],
        "scores":stat,
    }


def run(*, opener=None, model_module=None):
    try:
        raw=_read_source() if opener is None else _read_source(opener=opener)
        now=datetime.now(timezone.utc)
        rows, last=_parse(raw)
        train=[r for r in rows if r["date"]<=TRAIN_CUTOFF]
        holdout=[r for r in rows if r["date"]>=TEST_START]
        if model_module is None:
            from penaltyblog import models as model_module
        result=evaluate(train,holdout,model_module=model_module)
        return {
            "schema":SCHEMA,
            "status":"HOLD",
            "reason":"REAL_HISTORICAL_DATE_SPLIT_UNATTESTED_AND_UNCALIBRATED",
            "source_type":"real_public_historical_international_results",
            "historical_fixture_kickoff_utc_available":False,
            "original_a_native_international_producer_tested":False,
            "original_a_formula_reproduced_on_real_outcomes":True,
            "genuine_penaltyblog_models_trained_on_real_history":True,
            "source_sha256":hashlib.sha256(raw).hexdigest(),
            "source_git_blob_sha1_verified":True,
            "tested_result_asof_date_max":last.isoformat(),
            "training_cutoff_inclusive":TRAIN_CUTOFF,
            "heldout_start_inclusive":TEST_START,
            "heldout_end_inclusive":TEST_END,
            "train_contains_zero_test_results":True,
            "model_fit_uses_only_2025_real_scores":True,
            "sample_is_retrospective_not_original_signed_prematch":True,
            "market_odds_or_ev_verified":False,
            "certified_prospective_samples":0,
            "production_recommendations":"DISABLED",
            "positive_ev_verified":False,
            **result,
        }
    except Exception as exc:
        return {
            "schema":SCHEMA, "status":"HOLD",
            "reason":"REAL_HOLDOUT_TRIAL_FAILED",
            "failure_type":type(exc).__name__,
            "failure_detail":str(exc)[:140] if type(exc) is ValueError else None,
            "production_recommendations":"DISABLED",
            "certified_prospective_samples":0,
            "positive_ev_verified":False,
        }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True)
    args=p.parse_args(argv)
    result=run()
    path=Path(args.output)
    if path.exists() or path.is_symlink():
        raise ValueError("OUTPUT_ALREADY_EXISTS_OR_SYMLINK")
    raw=(json.dumps(result,ensure_ascii=False,sort_keys=True,
                    separators=(",",":"),allow_nan=False)+"\n").encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|
               getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as writer:
        writer.write(raw)
        writer.flush()
        os.fsync(writer.fileno())
    print("REAL_2026_NATIONAL_HELDOUT_RESULT",raw.decode().strip())
    return 0 if result.get("evaluated_real_2026_matches",0)>=MIN_TEST else 1


if __name__=="__main__":
    raise SystemExit(main())
