"""Research-only bivariate Poisson 1X2 / Asian lines / goals challenger.

Fits the *real optional Penaltyblog model* twice on the SAME pre-cutoff results:
  - original equal-weight training;
  - fixed 0.003/day time-decay training.
Never alters existing frozen A/Poisson/DC forecasts. No sportsbook inputs, EV,
market odds, xG, rollout, network calls, or data harvesting. Always HOLD.
"""
import argparse
import json
import math

from .penaltyblog_research_bridge import _timestamp, _unique_json, _validate

SCHEMA = "football-king-bivariate-goals-challenger-v1"
XI_PER_DAY = 0.003  # Research hypothesis, not optimised against held-out scores.
MAX_GOALS = 15
TOTAL_LINES = (2.5, 2.75, 3.0)
HOME_HANDICAPS = (-1.0, -0.75, -0.5, -0.25, 0.0, 0.25, 0.5, 0.75, 1.0)
SETTLEMENT = {-1.0: "full_loss", -0.5: "half_loss", 0.0: "push",
               0.5: "half_win", 1.0: "full_win"}


def _hold(reason, **details):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False, "model_promoted": False,
        "source_authenticity_verified": False,
        "independent_prematch_witness_verified": False,
        "independent_result_verification": False,
        "executable_bookmaker_odds_verified": False, **details,
    }


def _stake_result(adjusted):
    return 1.0 if adjusted > 0 else (-1.0 if adjusted < 0 else 0.0)


def _settle(kind, home, away, line):
    """Unit outcome from exact FT score, quarter lines split half the stake."""
    quarter = round(line * 4)
    if abs(line * 4 - quarter) > 1e-8:
        raise ValueError("INVALID_LINE")
    splits = ((quarter - 1) / 4, (quarter + 1) / 4) if quarter % 2 else (line,)
    outcome = 0.0
    for part in splits:
        adjusted = (home + away - part) if kind == "over" else (home - away + part)
        outcome += _stake_result(adjusted) / len(splits)
    key = round(outcome * 2) / 2
    if key not in SETTLEMENT or abs(key - outcome) > 1e-10:
        raise ValueError("INVALID_ASIAN_SETTLEMENT")
    return SETTLEMENT[key]


def _markets(matrix, kind, lines):
    reports = {}
    for line in lines:
        buckets = {name: 0.0 for name in SETTLEMENT.values()}
        for home, row in enumerate(matrix):
            for away, mass in enumerate(row):
                buckets[_settle(kind, home, away, line)] += mass
        if not math.isclose(sum(buckets.values()), 1.0, abs_tol=1e-7):
            raise ValueError("UNNORMALIZED_SETTLEMENT")
        reports[str(line)] = {name: round(value, 12) for name, value in buckets.items()}
    return reports


def _matrix(probability_grid):
    """Read the real upstream exact-score grid, enforce finite normalized mass."""
    raw = probability_grid.grid
    if len(raw) != MAX_GOALS:
        raise ValueError("INVALID_SCORE_GRID_SHAPE")
    matrix = []
    for row in raw:
        if len(row) != MAX_GOALS:
            raise ValueError("INVALID_SCORE_GRID_SHAPE")
        values = [float(value) for value in row]
        if any(not math.isfinite(x) or x < 0 or x > 1 for x in values):
            raise ValueError("INVALID_SCORE_GRID_VALUE")
        matrix.append(values)
    if not math.isclose(sum(sum(row) for row in matrix), 1.0, abs_tol=1e-7):
        raise ValueError("INVALID_SCORE_GRID_TOTAL")
    return matrix


def _result(matrix, probability_grid):
    calculated = [
        sum(matrix[h][a] for h in range(MAX_GOALS) for a in range(MAX_GOALS) if h > a),
        sum(matrix[h][h] for h in range(MAX_GOALS)),
        sum(matrix[h][a] for h in range(MAX_GOALS) for a in range(MAX_GOALS) if h < a),
    ]
    upstream = [float(x) for x in probability_grid.home_draw_away]
    if (len(upstream) != 3
            or any(not math.isfinite(x) or x < 0 or x > 1 for x in upstream)
            or any(abs(a - b) > 1e-6 for a, b in zip(upstream, calculated))):
        raise ValueError("INCONSISTENT_1X2_AND_SCORE_GRID")
    return {
        "probabilities_1x2_home_draw_away": [round(x, 12) for x in calculated],
        "over_total_goals_settlement": _markets(matrix, "over", TOTAL_LINES),
        "home_asian_handicap_settlement": _markets(matrix, "home_handicap", HOME_HANDICAPS),
    }


def compare(payload, *, model_factory=None):
    """Paired baseline and weighted bivariate fits on caller-provided history.

    model_factory is for synthetic contract tests only; live research imports
    Penaltyblog's BivariatePoissonGoalModel. Never return a certified pick.
    """
    required = {"schema", "production_recommendations", "model",
                "as_of_utc", "target_fixture", "historical_matches"}
    if (type(payload) is not dict or set(payload) != required
            or payload.get("schema") != SCHEMA
            or payload.get("production_recommendations") != "DISABLED"
            or payload.get("model") != "bivariate_poisson"):
        return _hold("INVALID_CONTRACT")

    # Existing validated bridge accepts poisson/DC identifiers. The temporary
    # alias is ONLY for data validation; NEVER used to fit either old model.
    validation = dict(payload)
    validation["schema"] = "football-king-penaltyblog-offline-input-v1"
    validation["model"] = "poisson"
    try:
        target, history = _validate(validation)
        cutoff = _timestamp(payload["as_of_utc"])
        ages = [(cutoff - _timestamp(row["kickoff_utc"])).total_seconds() / 86400
                for row in history]
        if any(not math.isfinite(x) or x <= 0 for x in ages):
            raise ValueError("INVALID_TRAINING_AGE")
        weights = [math.exp(-XI_PER_DAY * x) for x in ages]
        if any(not math.isfinite(w) or not 0 < w <= 1 for w in weights):
            raise ValueError("INVALID_DECAY_WEIGHTS")
    except (KeyError, TypeError, ValueError, OverflowError):
        return _hold("INVALID_OR_UNVERIFIED_INPUT")

    if model_factory is None:
        try:
            from penaltyblog import models
            model_factory = models.BivariatePoissonGoalModel
        except (ImportError, AttributeError):
            return _hold("OPTIONAL_PENALTYBLOG_NOT_INSTALLED")
    inputs = (
        [row["home_goals"] for row in history],
        [row["away_goals"] for row in history],
        [row["home_team_id"] for row in history],
        [row["away_team_id"] for row in history],
    )
    outputs = {}
    try:
        for label, training_weights in (("unweighted", None), ("time_weighted", weights)):
            options = {} if training_weights is None else {"weights": list(training_weights)}
            model = model_factory(*inputs, **options)
            model.fit()
            grid = model.predict(target["home_team_id"], target["away_team_id"],
                                 max_goals=MAX_GOALS, normalize=True)
            outputs[label] = _result(_matrix(grid), grid)
    except Exception:
        # Fail as a single cohort; do not publish one variant on partial fit.
        return _hold("BIVARIATE_FIT_OR_GRID_VALIDATION_FAILED")

    sum_weights = sum(weights)
    effective = sum_weights ** 2 / sum(weight * weight for weight in weights)
    return _hold(
        "UNVERIFIED_BIVARIATE_RESEARCH_ONLY",
        model_id="penaltyblog-bivariate-poisson-paired-decay-v1",
        fixture_id=target["event_id"], source_namespace=target["source_namespace"],
        league_id=target["league_id"], as_of_utc=payload["as_of_utc"],
        training_match_count=len(history),
        time_decay_xi_per_day=XI_PER_DAY,
        effective_weighted_sample_size=round(effective, 3),
        newest_training_age_days=round(min(ages), 3),
        oldest_training_age_days=round(max(ages), 3),
        models=outputs,
        market_settlement_contract="unit stake payout classes; no quoted odds or EV",
        note=("No performance advantage asserted: data source custody, fresh "
              "results, actual odds, live xG and independent walk-forward "
              "performance remain unverified."),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bivariate Poisson research HOLD")
    parser.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(
            fh, object_pairs_hook=_unique_json,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
        )
    print(json.dumps(compare(payload), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
