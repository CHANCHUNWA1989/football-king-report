"""Development-only Dixon-Coles low-score rho challenger.

Research sample receipt clocks and hashes are self-assertions; this code never
independently verifies historical fixtures, input availability, outcome truth,
external archives or calibration. Development scoreline log-loss selection is
IN-SAMPLE. Locked predictions are for future shadow research, never betting.
"""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone

from score_distribution_vnext import one_x_two, score_matrix

SCHEMA = "football-king-vnext-dc-development-challenger-v1"
MODEL_ID = "dc-scoreline-rho-grid-development-vnext-v1"
RHO_GRID = (-0.15, -0.10, -0.05, 0.0, 0.025)
MIN_DEVELOPMENT = 30
MAX_DEVELOPMENT = 3000
TRAIN_FIELDS = {
    "fixture_id", "kickoff_utc", "forecast_utc", "inputs_available_utc",
    "result_available_utc", "home_goals", "away_goals",
    "expected_home_goals", "expected_away_goals", "input_sha256"
}


def _clock(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("NAIVE_TIMESTAMP")
        return result.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc


def _id(value):
    return type(value) is str and 1 <= len(value) <= 128 and value.strip() == value and value.isprintable()


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _rate(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not .1 <= value <= 5.5:
        raise ValueError("INVALID_RATE")
    return float(value)


def _digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _development_row(row, cutoff):
    if type(row) is not dict or set(row) != TRAIN_FIELDS:
        raise ValueError("INVALID_DEVELOPMENT_SCHEMA")
    if not _id(row["fixture_id"]) or not _sha(row["input_sha256"]):
        raise ValueError("INVALID_DEVELOPMENT_ID_OR_HASH")
    kickoff, forecast, inputs, result = [_clock(row[k]) for k in (
        "kickoff_utc", "forecast_utc", "inputs_available_utc", "result_available_utc")]
    if not inputs <= forecast <= kickoff - timedelta(minutes=10):
        raise ValueError("TRAINING_FORECAST_LOOKAHEAD")
    if not kickoff + timedelta(minutes=90) <= result < cutoff:
        raise ValueError("TRAINING_OUTCOME_UNAVAILABLE_AT_FIT_CUTOFF")
    h, a = row["home_goals"], row["away_goals"]
    if (type(h) is not int or type(a) is not int
            or not 0 <= h <= 12 or not 0 <= a <= 12):
        raise ValueError("INVALID_TRAINING_SCORE")
    home_rate, away_rate = _rate(row["expected_home_goals"]), _rate(row["expected_away_goals"])
    return (row["fixture_id"], h, a, home_rate, away_rate)


def fit_development(rows, manifest, *, fit_cutoff_utc):
    """Fit on the declared *complete* development universe, no holdout labels.

    The manifest and timestamps lack independently witnessed provenance. A
    passing result is NOT evidence of out-of-sample improvement.
    """
    cutoff = _clock(fit_cutoff_utc)
    if type(rows) is not list or not MIN_DEVELOPMENT <= len(rows) <= MAX_DEVELOPMENT:
        raise ValueError("INSUFFICIENT_OR_EXCESSIVE_DEVELOPMENT_COHORT")
    if type(manifest) is not dict or set(manifest) != {
        "fixture_ids", "manifest_declared_utc", "development_cohort_id"
    }:
        raise ValueError("INVALID_DEVELOPMENT_MANIFEST")
    ids = manifest["fixture_ids"]
    if (type(ids) is not list or len(ids) != len(rows)
            or any(not _id(x) for x in ids) or len(set(ids)) != len(ids)
            or not _id(manifest["development_cohort_id"])
            or _clock(manifest["manifest_declared_utc"]) >= cutoff):
        raise ValueError("INCOMPLETE_OR_LATE_MANIFEST")
    parsed = [_development_row(row, cutoff) for row in rows]
    if len(set(x[0] for x in parsed)) != len(parsed) or set(ids) != {x[0] for x in parsed}:
        raise ValueError("DEVELOPMENT_MANIFEST_FIXTURE_MISMATCH")
    parsed.sort(key=lambda x: x[0])
    metrics = []
    for rho in RHO_GRID:
        losses = []
        for _, home, away, h_rate, a_rate in parsed:
            grid = score_matrix(h_rate, a_rate, rho=rho)
            if home >= len(grid) or away >= len(grid[0]):
                raise ValueError("TRAINING_SCORE_OUTSIDE_SUPPORTED_GRID")
            likelihood = grid[home][away]
            if likelihood <= 0:
                raise ValueError("INVALID_SCORELINE_LIKELIHOOD")
            losses.append(-math.log(likelihood))
        metrics.append({
            "rho": rho,
            "mean_development_scoreline_log_loss": math.fsum(losses) / len(losses),
        })
    winner = min(metrics, key=lambda item: (
        item["mean_development_scoreline_log_loss"], abs(item["rho"]), item["rho"]))
    manifest_digest = _digest({
        "manifest": manifest, "fit_cutoff_utc": cutoff.isoformat(),
        "development_rows": sorted(rows, key=lambda row: row["fixture_id"]),
        "rho_grid": RHO_GRID,
    })
    return {
        "schema": SCHEMA, "status": "DEVELOPMENT_ONLY",
        "model_id": MODEL_ID, "fit_cutoff_utc": cutoff.isoformat(),
        "selected_rho": winner["rho"], "development_n": len(parsed),
        "development_metric": "IN_SAMPLE_SCORELINE_LOG_LOSS",
        "grid_scores": metrics, "declared_manifest_sha256_unattested": manifest_digest,
        "parameter_refitting_permitted_on_past_forecasts": False,
        "manifest_independently_witnessed": False,
        "source_results_independently_verified": False,
        "out_of_sample_accuracy_improvement_verified": False,
        "model_calibrated": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def shadow_forecast(fitted, *, fixture_id, kickoff_utc, forecast_utc,
                    inputs_available_utc, home_rate, away_rate, input_sha256):
    """Issue a new, later, shadow-only forecast with a frozen development rho."""
    if (type(fitted) is not dict or fitted.get("schema") != SCHEMA
            or fitted.get("status") != "DEVELOPMENT_ONLY"
            or fitted.get("production_recommendations") != "DISABLED"
            or fitted.get("out_of_sample_accuracy_improvement_verified") is not False
            or fitted.get("model_calibrated") is not False
            or fitted.get("selected_rho") not in RHO_GRID
            or not _sha(fitted.get("declared_manifest_sha256_unattested"))):
        raise ValueError("INVALID_FROZEN_CHALLENGER")
    fit_time, kickoff, prediction, inputs = [
        _clock(x) for x in (fitted["fit_cutoff_utc"], kickoff_utc, forecast_utc,
                            inputs_available_utc)]
    if (not _id(fixture_id) or not _sha(input_sha256)
            or not fit_time < inputs <= prediction <= kickoff - timedelta(minutes=10)):
        raise ValueError("PROSPECTIVE_FORECAST_TIME_OR_IDENTITY_CONFLICT")
    home, away = _rate(home_rate), _rate(away_rate)
    probabilities = one_x_two(score_matrix(home, away, rho=fitted["selected_rho"]))
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY", "model_id": MODEL_ID,
        "fixture_id": fixture_id, "kickoff_utc": kickoff.isoformat(),
        "forecast_utc": prediction.isoformat(), "source_fit_cutoff_utc": fit_time.isoformat(),
        "selected_rho": fitted["selected_rho"], "probabilities_1x2": probabilities,
        "development_manifest_sha256_unattested": fitted["declared_manifest_sha256_unattested"],
        "input_sha256_unattested": input_sha256,
        "historical_forecast_reconstruction_allowed": False,
        "independently_authenticated_inputs": False,
        "model_calibrated": False,
        "out_of_sample_accuracy_improvement_verified": False,
        "model_scoring_eligible": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def audit_fit(rows, manifest, *, fit_cutoff_utc):
    try:
        return fit_development(rows, manifest, fit_cutoff_utc=fit_cutoff_utc)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {
            "schema": SCHEMA, "status": "HOLD", "reason": str(exc) or "INVALID_INPUT",
            "model_calibrated": False,
            "out_of_sample_accuracy_improvement_verified": False,
            "positive_ev_verified": False,
            "production_recommendations": "DISABLED",
        }


def audit_shadow_forecast(fitted, **kwargs):
    try:
        return shadow_forecast(fitted, **kwargs)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {
            "schema": SCHEMA, "status": "HOLD", "reason": str(exc) or "INVALID_INPUT",
            "model_calibrated": False,
            "out_of_sample_accuracy_improvement_verified": False,
            "positive_ev_verified": False,
            "production_recommendations": "DISABLED",
        }
