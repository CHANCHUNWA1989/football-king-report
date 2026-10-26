"""Isolated low-score correction of rounded historical replay goal rates.

This is not a jointly fitted attack/defence Dixon–Coles model. Its inputs are
the replay's five-decimal expected-goal rates, not a sealed score distribution
or independently verified goal-distribution evidence. No production model or
previously issued forecast is changed by this retrospective experiment.
"""
import copy
import math
from datetime import date

MODEL_ID = "dixon-coles-5dp-retrospective-v1"
SCHEMA = "football-king-retrospective-dixon-coles-v1"
DEVELOPMENT = "2024-25"
ASSESSMENT = "2025-26"
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
# Declared before assessment: one global rho, never per-league refitting.
RHO_GRID = (-0.15, -0.10, -0.05, 0.0, 0.025)
FIT_BASIS = "2024_25_DEVELOPMENT_UNROUNDED_LOG_LOSS_ONLY"


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, ValueError):
        return False


def _probabilities_unrounded(home_rate, away_rate, rho):
    if not all(_finite_number(v) and .1 <= v <= 5.5
               for v in (home_rate, away_rate)):
        raise ValueError("DIXON_COLES_RATE_OUT_OF_RANGE")
    if not _finite_number(rho):
        raise ValueError("INVALID_DIXON_COLES_RHO")
    tau = {
        (0, 0): 1-home_rate*away_rate*rho,
        (0, 1): 1+home_rate*rho,
        (1, 0): 1+away_rate*rho,
        (1, 1): 1-rho,
    }
    if not all(_finite_number(v) and v > 0 for v in tau.values()):
        raise ValueError("NONPOSITIVE_DIXON_COLES_TAU")
    # Keep the published model's finite grid and aggregation order. rho=0
    # therefore exactly reproduces poisson_1x2 for the SAME input rates.
    home = [math.exp(-home_rate)*home_rate**i/math.factorial(i) for i in range(12)]
    away = [math.exp(-away_rate)*away_rate**i/math.factorial(i) for i in range(12)]
    values = [0.0, 0.0, 0.0]
    for h, ph in enumerate(home):
        for a, pa in enumerate(away):
            values[0 if h > a else 1 if h == a else 2] += ph*pa*tau.get((h, a), 1.0)
    total = sum(values)
    if not _finite_number(total) or total <= 0:
        raise ValueError("INVALID_DIXON_COLES_MASS")
    return [v/total for v in values]


def probabilities(home_rate, away_rate, rho):
    """Correct four low-score cells, normalize the 12×12 grid, round to 7dp."""
    return [round(v, 7) for v in _probabilities_unrounded(home_rate, away_rate, rho)]


def _validate_rows(rows, season):
    if not isinstance(rows, (list, tuple)):
        raise ValueError("INVALID_DIXON_COLES_ROWS")
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or row.get("season") != season
                or row.get("league") not in LEAGUES
                or type(row.get("y")) is not int or row["y"] not in (0, 1, 2)):
            raise ValueError("INVALID_DIXON_COLES_COHORT")
        try:
            date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError):
            raise ValueError("INVALID_DIXON_COLES_DATE") from None
        for key in ("original", "league_frequency"):
            p = row.get(key)
            if (not isinstance(p, (list, tuple)) or len(p) != 3
                    or not all(_finite_number(v) and 0 < v <= 1 for v in p)
                    or abs(sum(p)-1) > .002):
                raise ValueError("INVALID_DIXON_COLES_PROBABILITIES")
        for key in ("expected_home_goals", "expected_away_goals"):
            if not (_finite_number(row.get(key)) and .1 <= row[key] <= 5.5):
                raise ValueError("DIXON_COLES_RATE_OUT_OF_RANGE")
        case_id = row.get("replay_case_id")
        if isinstance(case_id, str) and case_id.strip():
            if case_id in seen:
                raise ValueError("DUPLICATE_REPLAY_CASE_ID")
            seen.add(case_id)


def fit_development(rows):
    """Select one rho by unrounded 2024/25 mean log loss; no assessment input."""
    _validate_rows(rows, DEVELOPMENT)
    if not rows:
        return {"rho": None, "scores": [], "n": 0,
                "basis": FIT_BASIS, "status": "HOLD"}
    scores = []
    for rho in RHO_GRID:
        loss = math.fsum(-math.log(_probabilities_unrounded(
            row["expected_home_goals"], row["expected_away_goals"], rho)[row["y"]])
            for row in rows)/len(rows)
        scores.append({"rho": rho, "development_mean_log_loss": loss})
    winner = min(scores, key=lambda item: (
        item["development_mean_log_loss"], abs(item["rho"]), item["rho"]))
    return {"rho": winner["rho"], "scores": scores, "n": len(rows),
            "basis": FIT_BASIS, "status": "DEVELOPMENT_FIT_ONLY"}


def _scope(rows, rho):
    # Local imports avoid a cycle when retrospective_backtest builds this
    # report, including when it is invoked as a __main__ CLI module.
    from retrospective_backtest import summary, block_ci
    from research_center import calibration, score_rps

    models = {}
    for key in ("original", "derived_rho0", "candidate", "league_frequency"):
        if not rows or (key == "candidate" and rho is None):
            models[key] = None
            continue
        # Tuple inputs are accepted by the validator, but existing score_rps
        # deliberately requires a probability list.
        models[key] = {**summary(rows, key),
                       "mean_normalized_rps": round(math.fsum(
                           score_rps(list(row[key]), row["y"]) for row in rows)/len(rows), 6),
                       "probability_calibration": calibration([
                           {"p": row[key], "y": row["y"]} for row in rows])}
    differences = [abs(row["original"][i]-row["derived_rho0"][i])
                   for row in rows for i in range(3)]
    paired_original = paired_derived = None
    if rows and rho is not None:
        paired_original = block_ci(rows, "candidate")
        aliases = [{**row, "original": row["derived_rho0"]} for row in rows]
        paired_derived = block_ci(aliases, "candidate")
    return {
        "n": len(rows), "models": models,
        "rho0_original_approximation": {
            "n": len(rows),
            "maximum_absolute_probability_difference": max(differences) if differences else None,
            "argmax_disagreements": sum(
                max(range(3), key=lambda i: row["original"][i]) !=
                max(range(3), key=lambda i: row["derived_rho0"][i]) for row in rows),
        },
        "paired_week_bootstrap_candidate_vs_original": paired_original,
        "paired_week_bootstrap_candidate_vs_derived_rho0": paired_derived,
    }


def build_report(development_rows, assessment_rows, *, archive_complete=True):
    """Evaluate a development-fitted correction on already inspected history.

    archive_complete must be False when the parent archive loader reports any
    missing or invalid scope. A partial archive cannot silently fit a different
    candidate. The existing replay remains available for diagnostics.
    """
    if type(archive_complete) is not bool:
        raise ValueError("INVALID_DIXON_COLES_ARCHIVE_COMPLETENESS")
    _validate_rows(development_rows, DEVELOPMENT)
    _validate_rows(assessment_rows, ASSESSMENT)
    known = [row["replay_case_id"] for row in (*development_rows, *assessment_rows)
             if isinstance(row.get("replay_case_id"), str) and row["replay_case_id"].strip()]
    if len(set(known)) != len(known):
        raise ValueError("DUPLICATE_REPLAY_CASE_ID")
    ready = archive_complete and bool(development_rows) and bool(assessment_rows)
    fit = fit_development(development_rows) if ready else {
        "rho": None, "scores": [], "n": len(development_rows),
        "basis": FIT_BASIS, "status": "HOLD"}
    rho = fit["rho"]
    cohorts = {DEVELOPMENT: copy.deepcopy(list(development_rows)),
               ASSESSMENT: copy.deepcopy(list(assessment_rows))}
    for rows in cohorts.values():
        for row in rows:
            rates = (row["expected_home_goals"], row["expected_away_goals"])
            row["derived_rho0"] = probabilities(*rates, 0.0)
            if rho is not None:
                row["candidate"] = probabilities(*rates, rho)
    by_league = {}
    for league in LEAGUES:
        if not any(row["league"] == league for rows in cohorts.values() for row in rows):
            continue
        by_league[league] = {"selected_rho": rho, **{
            season: _scope([row for row in rows if row["league"] == league], rho)
            for season, rows in cohorts.items()}}
    return {
        "schema": SCHEMA, "model_id": MODEL_ID,
        "status": "EXPLORATORY_RESEARCH_ONLY" if ready else "HOLD",
        "hold_reason": None if ready else "INCOMPLETE_ARCHIVE_OR_EMPTY_COHORT",
        "archive_complete": archive_complete,
        "selected_rho": rho, "prespecified_global_rho_grid": list(RHO_GRID),
        "development_season": DEVELOPMENT, "assessment_season": ASSESSMENT,
        "development_fit": fit,
        "cohorts": {season: _scope(rows, rho) for season, rows in cohorts.items()},
        "by_league": by_league,
        "evaluation_type": "FIXED_RATE_RETROSPECTIVE_LOW_SCORE_CORRECTION",
        "goal_rates_are_rounded_replay_approximations": True,
        "sealed_score_distribution_reconstructed": False,
        "joint_attack_defence_dixon_coles_fit": False,
        "development_rho_score_is_in_sample": True,
        "assessment_is_unseen_holdout": False,
        "assessment_has_already_been_inspected": True,
        "uses_assessment_labels_for_rho_selection": False,
        "source_results_independently_verified": False,
        "authentic_prematch_predictions": False,
        "model_calibration_certified": False,
        "market_baseline_available": False,
        "betting_roi_estimable": False,
        "automatic_model_promotion": False,
        "production_recommendations": "DISABLED",
        "confidence_interval_direction": {
            "hit_rate_gain": "CANDIDATE_MINUS_NAMED_BASELINE",
            "log_loss_gain": "NAMED_BASELINE_MINUS_CANDIDATE",
            "positive_values": "CANDIDATE_BETTER"},
        "bootstrap_conditioning": "FIXED_SELECTED_RHO_EXCLUDES_FIT_AND_SELECTION_UNCERTAINTY",
        "limitations": [
            "Fixed-rate correction only; goal rates come from five-decimal retrospective replay output.",
            "Compare against derived rho=0 first; published original probabilities may differ due to rate rounding.",
            "2024/25 rho performance is in-sample even though base rates use earlier calendar days.",
            "2025/26 outcomes were already inspected before choosing this model family; exploratory historical assessment only.",
            "Weekly paired bootstrap conditions on the fitted rho and excludes fitting/model-selection uncertainty.",
            "Date-only source-revisable archives do not establish authentic pre-match evidence or certified regular-90-minute results.",
            "No market advantage, executable prices, ROI, forward calibration, or automatic production promotion is established.",
        ],
    }
