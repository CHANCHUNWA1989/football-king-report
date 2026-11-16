"""2025-only trained dynamic Poisson vs DC on previously inspected 2026 scores.

Exploratory 186-match date-only retrospective OOS. Source is the preexisting
Git-blob-pinned public national-team CSV. Not truly prematch witnessed and
NOT an untouched confirmatory holdout; no sportsbook quotes, xG or EV.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
import os
import random
from pathlib import Path

from .dynamic_score_driven_poisson import (
    date_only_diagnostic_rates, score_grid, MODEL_ID,
)
from .live_uefa_nations_three_model_probe import _read_source, _parse
from .live_uefa_2026_holdout_test import (
    _original_a_real_rates, _original_a_real_formula,
    TRAIN_CUTOFF, TEST_START, TEST_END,
)
from .penaltyblog_bivariate_goals_challenger import _matrix, _result, MAX_GOALS
from .real_2026_three_market_oos import (
    _score, _baseline, _direction, _actual_grade,
    _distribution, TYPES, CLASSES_1X2,
)

SCHEMA = "football-king-dynamic-poisson-2026-date-only-audit-v1"
MODELS = ("original_A", "poisson", "dixon_coles", "dynamic_score_poisson")
CLASSES = {
    "1X2": CLASSES_1X2, "OVER_2.75": TYPES, "HOME_AH_-0.25": TYPES,
}
MARKET_DEFS = {
    "OVER_2.75": ("TOTAL_OVER_2.75", "TOTAL", "OVER", 2.75),
    "HOME_AH_-0.25": ("AH_HOME_-0.25", "AH", "HOME", -0.25),
}
GRADE_UPPER = {"full_win": "FULL_WIN", "half_win": "HALF_WIN",
               "push": "PUSH", "half_loss": "HALF_LOSS",
               "full_loss": "FULL_LOSS"}
BOOTSTRAPS = 2000
RNG_SEED = 20261117


def _hold(reason, **data):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED", "positive_ev_verified": False,
        "model_promoted": False, "certified_prospective_samples": 0,
        "historical_market_roi_or_ev_verified": False,
        "original_holdout_untouched_confirmatory": False,
        "independently_timestamped_prematch_vectors": False,
        "real_quote_prices_verified": False,
        **data,
    }


def _verify_rows(rows, lower, upper):
    if type(rows) is not list:
        raise ValueError("INVALID_DATE_SPLIT")
    keys = set()
    for row in rows:
        if (type(row) is not dict or
                type(row.get("date")) is not str or
                not lower <= row["date"] <= upper or
                date.fromisoformat(row["date"]).isoformat() != row["date"] or
                type(row.get("home")) is not str or not row["home"] or
                type(row.get("away")) is not str or not row["away"] or
                row["home"] == row["away"] or
                type(row.get("score_ft")) is not list or
                len(row["score_ft"]) != 2 or
                any(type(g) is not int or not 0 <= g <= 20 for g in row["score_ft"])):
            raise ValueError("INVALID_DATE_ONLY_INPUT")
        key = (row["date"], row["home"], row["away"])
        if key in keys:
            raise ValueError("DUPLICATE_DATE_ONLY_EVENT")
        keys.add(key)


def _quantile(values, fraction):
    pos = (len(values) - 1) * fraction
    lower = int(math.floor(pos))
    upper = int(math.ceil(pos))
    return values[lower] if lower == upper else (
        values[lower] * (upper - pos) + values[upper] * (pos - lower))


def _paired_ci(days, losses_new, losses_dc, *, metric_key):
    if len(days) != len(losses_new) or len(days) != len(losses_dc):
        raise ValueError("UNPAIRED_MATCHES")
    by_day = defaultdict(list)
    for day, new, baseline in zip(days, losses_new, losses_dc):
        by_day[day].append(new - baseline)
    daily = [(sum(by_day[d]), len(by_day[d])) for d in sorted(by_day)]
    point = sum(a - b for a, b in zip(losses_new, losses_dc)) / len(days)
    if len(daily) < 5:
        return {"mean_delta": round(point, 6), "interval_95pct": None,
                "includes_zero": None, "distinct_date_clusters": len(daily)}
    rng = random.Random(RNG_SEED + metric_key)
    distribution = []
    for _ in range(BOOTSTRAPS):
        choices = [daily[rng.randrange(len(daily))] for _ in daily]
        distribution.append(sum(x[0] for x in choices) / sum(x[1] for x in choices))
    distribution.sort()
    low, high = _quantile(distribution, 0.025), _quantile(distribution, 0.975)
    return {
        "mean_delta": round(point, 6),
        "interval_95pct": [round(low, 6), round(high, 6)],
        "includes_zero": low <= 0 <= high,
        "distinct_date_clusters": len(daily),
    }


def evaluate(train, heldout, *, model_module, min_train=200, min_test=150):
    _verify_rows(train, "2025-01-01", TRAIN_CUTOFF)
    _verify_rows(heldout, TEST_START, TEST_END)
    if len(train) < min_train or len(heldout) < min_test:
        raise ValueError("NOT_ENOUGH_REAL_DATE_SPLIT_RESULTS")
    appearances = Counter()
    for row in train:
        appearances.update((row["home"], row["away"]))
    eligible = [r for r in heldout
                if appearances[r["home"]] >= 5 and appearances[r["away"]] >= 5]
    if len(eligible) < min_test:
        raise ValueError("INSUFFICIENT_PREDECLARED_TEAM_COVERAGE")
    fitted = {}
    for name, klass in (
        ("poisson", model_module.PoissonGoalsModel),
        ("dixon_coles", model_module.DixonColesGoalModel),
    ):
        model = klass(
            [r["score_ft"][0] for r in train],
            [r["score_ft"][1] for r in train],
            [r["home"] for r in train],
            [r["away"] for r in train],
        )
        model.fit()
        fitted[name] = model
    observed = {
        "1X2": [_direction(r["score_ft"]) for r in eligible],
        **{market: [_actual_grade(r, definition) for r in eligible]
           for market, definition in MARKET_DEFS.items()},
    }
    forecasts = {
        name: {market: [] for market in CLASSES} for name in MODELS
    }

    def put(model_name, matrix_report):
        forecasts[model_name]["1X2"].append(dict(zip(
            CLASSES_1X2, matrix_report["p_home_draw_away"])))
        forecasts[model_name]["OVER_2.75"].append({
            GRADE_UPPER[k]: v for k, v in
            matrix_report["over_total_goals_settlement"]["2.75"].items()})
        forecasts[model_name]["HOME_AH_-0.25"].append({
            GRADE_UPPER[k]: v for k, v in
            matrix_report["home_asian_handicap_settlement"]["-0.25"].items()})

    for row in eligible:
        h, a = row["home"], row["away"]
        # One unmodified 2025-only original A formula, verified against prior
        # implementation; never fitted to a 2026 outcome or changed retrospectively.
        rates = _original_a_real_rates(train, h, a)
        from .shadow_forecast import poisson_1x2
        a_prob = poisson_1x2(*rates)
        old_formula = _original_a_real_formula(train, h, a)
        if max(abs(x-y) for x, y in zip(a_prob, old_formula)) > 1e-8:
            raise ValueError("ORIGINAL_A_SCORE_DRIFT")
        forecasts["original_A"]["1X2"].append(dict(zip(CLASSES_1X2, a_prob)))
        for name, definition in MARKET_DEFS.items():
            forecasts["original_A"][name].append(
                _distribution(rates[0], rates[1], definition))
        for name, model in fitted.items():
            grid = model.predict(h, a, max_goals=MAX_GOALS, normalize=True)
            report = _result(_matrix(grid), grid)
            put(name, {
                "p_home_draw_away": report["probabilities_1x2_home_draw_away"],
                "over_total_goals_settlement": report["over_total_goals_settlement"],
                "home_asian_handicap_settlement": report["home_asian_handicap_settlement"],
            })
        dynamic_rates = date_only_diagnostic_rates(
            train, h, a, date.fromisoformat(row["date"]))
        put("dynamic_score_poisson", score_grid(*dynamic_rates))

    results, paired = {}, {}
    days = [r["date"] for r in eligible]
    for model_name in MODELS:
        results[model_name] = {}
        for market, classes in CLASSES.items():
            losses = [_score(p, outcome, classes)
                      for p, outcome in zip(
                          forecasts[model_name][market], observed[market])]
            n = len(losses)
            results[model_name][market] = {
                "n": n,
                "mean_brier": round(sum(x[0] for x in losses) / n, 6),
                "mean_logloss": round(sum(x[1] for x in losses) / n, 6),
                "top_1_accuracy": (
                    round(sum(max(p, key=p.get) == outcome for p, outcome in
                              zip(forecasts[model_name][market], observed[market])) / n, 6)
                    if market == "1X2" else None),
            }
    for ix, (market, classes) in enumerate(CLASSES.items()):
        scores = {}
        for model_name in ("dynamic_score_poisson", "dixon_coles"):
            scores[model_name] = [
                _score(p, outcome, classes) for p, outcome in zip(
                    forecasts[model_name][market], observed[market])]
        paired[market] = {}
        for metric_idx, metric in enumerate(("brier", "logloss")):
            paired[market][metric] = _paired_ci(
                days,
                [item[metric_idx] for item in scores["dynamic_score_poisson"]],
                [item[metric_idx] for item in scores["dixon_coles"]],
                metric_key=10 * ix + metric_idx,
            )
    return {
        "training_real_matches": len(train),
        "source_test_rows": len(heldout),
        "same_eligible_heldout_games": len(eligible),
        "excluded_due_to_2025_training_coverage": len(heldout) - len(eligible),
        "test_scores_passed_to_model_fit": False,
        "date_only_retrospective_no_publisher_time_authentication": True,
        "dynamic_model_id": MODEL_ID,
        "frozen_hyperparameters_preexisting_186_analysis": True,
        "tested_models": list(MODELS),
        "market_lines_are_fixed_hypothetical_not_actual_quotes": [
            "1X2", "OVER_2.75", "HOME_AH_-0.25",
        ],
        "per_model_scores": results,
        "dynamic_minus_dixon_coles_paired_date_cluster_CI95": paired,
        "bootstrap_draws": BOOTSTRAPS,
    }


def audit(*, reader=_read_source, model_module=None):
    try:
        original = reader()
        rows, latest = _parse(original)
        train = [r for r in rows if r["date"] <= TRAIN_CUTOFF]
        heldout = [r for r in rows if r["date"] >= TEST_START]
        if model_module is None:
            from penaltyblog import models as model_module
        details = evaluate(train, heldout, model_module=model_module)
        if any(details[k] != v for k, v in (
            ("training_real_matches", 260),
            ("source_test_rows", 186),
            ("same_eligible_heldout_games", 186),
        )):
            raise ValueError("PINNED_HISTORICAL_COHORT_DRIFTED")
        return _hold(
            "EXPLORATORY_REUSED_2026_RESULTS_NOT_CERTIFIED_FORWARD_TEST",
            source_sha256=hashlib.sha256(original).hexdigest(),
            latest_public_result_date=latest.isoformat(),
            **details,
        )
    except Exception as exc:
        return _hold(
            "REAL_DYNAMIC_2026_AUDIT_BLOCKED",
            failure_class=type(exc).__name__,
            safe_detail=str(exc)[:140] if type(exc) is ValueError else None,
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    out = Path(args.output)
    if out.exists() or out.is_symlink():
        raise ValueError("EXISTING_AUDIT_CANNOT_BE_REWRITTEN")
    report = audit()
    body = (json.dumps(report, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as writer:
        writer.write(body)
        writer.flush()
        os.fsync(writer.fileno())
    print("DYNAMIC_DATE_SPLIT_RESEARCH", body.decode().strip())
    return 0 if report.get("same_eligible_heldout_games") == 186 else 1


if __name__ == "__main__":
    raise SystemExit(main())
