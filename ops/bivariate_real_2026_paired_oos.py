"""Real-result 2025->2026 date-split exploratory three-market model comparison.

Reuses the pinned public source from the existing 2026 international holdout.
This 186-match holdout was *already inspected by project research* and is NOT
an untouched confirmatory or third-party witnessed prospective test. No odds.
Never merge/promote from this diagnostic or revise 2026-11-15 frozen vectors.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math

from .live_uefa_nations_three_model_probe import _read_source, _parse
from .live_uefa_2026_holdout_test import (
    _original_a_real_formula, _original_a_real_rates,
    TRAIN_CUTOFF, TEST_START, TEST_END,
)
from .real_2026_three_market_oos import (
    _baseline, _score, _actual_grade, _distribution, _direction,
    CLASSES_1X2, TYPES,
)
from .penaltyblog_bivariate_goals_challenger import (
    _matrix, _result, MAX_GOALS, XI_PER_DAY,
)
from .bivariate_paired_uncertainty import evaluate as evaluate_paired_uncertainty

SCHEMA = "football-king-2026-bivariate-paired-date-split-v1"
MODEL_NAMES = ("original_A", "poisson", "dixon_coles",
               "bivariate_poisson", "bivariate_poisson_time_decay")
MARKETS = (
    ("1X2", ("HOME", "DRAW", "AWAY")),
    ("TOTAL_OVER_2.75", TYPES),
    ("AH_HOME_-0.25", TYPES),
)
MARKET_DEFS = {
    "TOTAL_OVER_2.75": ("TOTAL_OVER_2.75", "TOTAL", "OVER", 2.75),
    "AH_HOME_-0.25": ("AH_HOME_-0.25", "AH", "HOME", -0.25),
}
GRADE_UPPER = {"full_win": "FULL_WIN", "half_win": "HALF_WIN",
               "push": "PUSH", "half_loss": "HALF_LOSS",
               "full_loss": "FULL_LOSS"}


def _hold(reason, **data):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED", "model_promoted": False,
        "positive_ev_verified": False, "historical_market_roi_or_ev_verified": False,
        "certified_prospective_samples": 0,
        "external_prematch_timestamps_verified": False,
        "source_result_publication_times_verified": False,
        "original_holdout_is_untouched_confirmatory": False, **data,
    }


def _valid(rows, start, end):
    if not isinstance(rows, list):
        raise ValueError("INVALID_REAL_COHORT")
    seen = set()
    for r in rows:
        if (type(r) is not dict or type(r.get("date")) is not str
                or not start <= r["date"] <= end
                or type(r.get("home")) is not str or not r["home"]
                or type(r.get("away")) is not str or not r["away"]
                or r["home"] == r["away"]
                or type(r.get("score_ft")) is not list
                or len(r["score_ft"]) != 2
                or any(type(g) is not int or not 0 <= g <= 20
                       for g in r["score_ft"])):
            raise ValueError("INVALID_REAL_SCORE_OR_DATE")
        key = (r["date"], r["home"], r["away"])
        if key in seen:
            raise ValueError("DUPLICATE_REAL_MATCH")
        seen.add(key)


def _summary(observed, forecasts, baseline, classes):
    if len(observed) != len(forecasts) or not observed:
        raise ValueError("INCOMPLETE_PAIRED_TEST_COHORT")
    n = len(observed)
    values = [_score(p, o, classes) for p, o in zip(forecasts, observed)]
    base = [_score(baseline, o, classes) for o in observed]
    return {
        "n": n,
        "mean_brier": round(sum(x[0] for x in values) / n, 6),
        "mean_logloss": round(sum(x[1] for x in values) / n, 6),
        "train_only_frequency_baseline_brier": round(sum(x[0] for x in base) / n, 6),
        "train_only_frequency_baseline_logloss": round(sum(x[1] for x in base) / n, 6),
        "top_class_accuracy": (
            round(sum(max(p, key=p.get) == o for p, o in zip(forecasts, observed)) / n, 6)
            if len(classes) == 3 else None),
    }


def _fit(model_module, key, train, weights):
    constructors = {
        "poisson": model_module.PoissonGoalsModel,
        "dixon_coles": model_module.DixonColesGoalModel,
        "bivariate_poisson": model_module.BivariatePoissonGoalModel,
        "bivariate_poisson_time_decay": model_module.BivariatePoissonGoalModel,
    }
    options = {"weights": weights} if key.endswith("_time_decay") else {}
    model = constructors[key](
        [r["score_ft"][0] for r in train],
        [r["score_ft"][1] for r in train],
        [r["home"] for r in train],
        [r["away"] for r in train],
        **options,
    )
    model.fit()
    return model


def evaluate(train, heldout, *, model_module, min_train=200, min_test=150):
    """Only historical 2025 score arrays ever enter model.fit.

    This comparison is exploratory because earlier project experiments already
    examined the same heldout year. Not independently witnessed forecasts.
    """
    _valid(train, "2025-01-01", TRAIN_CUTOFF)
    _valid(heldout, TEST_START, TEST_END)
    if (len(train) < min_train or len(heldout) < min_test
            or not 1 <= min_test <= len(heldout)):
        raise ValueError("INSUFFICIENT_DATE_SPLIT")
    appearances = Counter()
    for row in train:
        appearances[row["home"]] += 1
        appearances[row["away"]] += 1
    test = [row for row in heldout
            if appearances[row["home"]] >= 5 and appearances[row["away"]] >= 5]
    if len(test) < min_test:
        raise ValueError("INSUFFICIENT_PAIRED_TEAM_COVERAGE")
    as_of = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ages = [(as_of - datetime.fromisoformat(r["date"]).replace(tzinfo=timezone.utc))
            .total_seconds() / 86400.0 for r in train]
    if any(age <= 0 or not math.isfinite(age) for age in ages):
        raise ValueError("INVALID_RETROSPECTIVE_AGE")
    weights = [math.exp(-XI_PER_DAY * age) for age in ages]
    fitted = {name: _fit(model_module, name, train, weights)
              for name in MODEL_NAMES if name != "original_A"}
    observed = {
        "1X2": [_direction(row["score_ft"]) for row in test],
        **{name: [_actual_grade(row, MARKET_DEFS[name]) for row in test]
           for name in MARKET_DEFS},
    }
    forecasts = {name: {market: [] for market, _ in MARKETS} for name in MODEL_NAMES}
    for row in test:
        h, a = row["home"], row["away"]
        a_probs = _original_a_real_formula(train, h, a)
        forecasts["original_A"]["1X2"].append(dict(zip(CLASSES_1X2, a_probs)))
        a_home, a_away = _original_a_real_rates(train, h, a)
        for market in MARKET_DEFS:
            forecasts["original_A"][market].append(
                _distribution(a_home, a_away, MARKET_DEFS[market]))
        for name, model in fitted.items():
            grid = model.predict(h, a, max_goals=MAX_GOALS, normalize=True)
            prob = _result(_matrix(grid), grid)
            forecasts[name]["1X2"].append(dict(zip(
                CLASSES_1X2, prob["probabilities_1x2_home_draw_away"])))
            forecasts[name]["TOTAL_OVER_2.75"].append({
                GRADE_UPPER[k]: v for k, v in
                prob["over_total_goals_settlement"]["2.75"].items()})
            forecasts[name]["AH_HOME_-0.25"].append({
                GRADE_UPPER[k]: v for k, v in
                prob["home_asian_handicap_settlement"]["-0.25"].items()})
    scored = {}
    for name in MODEL_NAMES:
        scored[name] = {}
        for market, classes in MARKETS:
            baseline = (_baseline(train, "1X2") if market == "1X2" else
                        _baseline(train, "AH_OR_OU", MARKET_DEFS[market]))
            scored[name][market] = _summary(
                observed[market], forecasts[name][market], baseline, classes)
    # Same fixture IDs / exact same held-out score labels for every model.
    # This is descriptive paired uncertainty on a REUSED date-split, never a
    # model-selection acceptance test or verified prospective performance.
    paired_uncertainty = evaluate_paired_uncertainty(
        [row["date"] for row in test], observed, forecasts)
    return {
        "paired_uncertainty": paired_uncertainty,
        "training_games": len(train), "heldout_source_games": len(heldout),
        "paired_test_games": len(test),
        "excluded_under_five_training_appearances": len(heldout) - len(test),
        "train_year": 2025, "test_year": 2026,
        "date_split_only_not_true_witnessed_prematch": True,
        "same_training_year_for_all_models": True,
        "fixed_unoptimised_decay_xi_per_day": XI_PER_DAY,
        "fixed_hypothetical_markets_not_tradable_quotes": [
            "1X2", "OVER_2.75", "AH_HOME_-0.25"],
        "model_reports": scored,
    }


def audit(*, source_reader=_read_source, model_module=None):
    try:
        raw = source_reader()
        rows, latest = _parse(raw)
        train = [row for row in rows if row["date"] <= TRAIN_CUTOFF]
        heldout = [row for row in rows if row["date"] >= TEST_START]
        if model_module is None:
            from penaltyblog import models as model_module
        result = evaluate(train, heldout, model_module=model_module)
        if (result["training_games"] != 260 or result["heldout_source_games"] != 186
                or result["paired_test_games"] != 186):
            raise ValueError("PINNED_REAL_COHORT_NOT_EXPECTED")
        return _hold(
            "REAL_EXPLORATORY_REUSED_DATE_SPLIT_NO_MARKET_ODDS",
            historical_source="pinned_martj42_international_results",
            historical_source_git_blob_verified_by_existing_reader=True,
            source_sha256=hashlib.sha256(raw).hexdigest(),
            latest_public_row_date=latest.isoformat(),
            **result,
        )
    except Exception as exc:
        return _hold("REAL_PAIRED_DATE_SPLIT_BLOCKED",
                     failure_type=type(exc).__name__,
                     safe_detail=str(exc)[:140] if type(exc) is ValueError else None)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = audit()
    from pathlib import Path
    import os
    path = Path(args.output)
    if path.exists() or path.is_symlink():
        raise ValueError("NO_REWRITE_OF_EXISTING_RESEARCH_OUTPUT")
    encoded = (json.dumps(report, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(encoded)
        fh.flush()
        os.fsync(fh.fileno())
    print("EXPLORATORY_REAL_BIVARIATE_OOS", encoded.decode().strip())
    return 0 if report.get("paired_test_games") == 186 else 1


if __name__ == "__main__":
    raise SystemExit(main())
