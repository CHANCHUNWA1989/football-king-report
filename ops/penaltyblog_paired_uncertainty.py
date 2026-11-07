"""Paired, fixture-aligned bootstrap uncertainty for research-only 1X2 forecasts.

Positive delta means Dixon-Coles has lower loss than Poisson.
Bootstrap resamples fixtures as pairs, never models independently. It is
illustrative IID uncertainty, NOT proof of generalization or profitability.
"""
import math
import random

from .offline_1x2_validation import evaluate_1x2
from .penaltyblog_research_bridge import _timestamp

MODELS = ("poisson", "dixon_coles")
OUTCOMES = ("H", "D", "A")


def _hold(reason, **details):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "model_promoted": False,
            "independent_provenance_verified": False, **details}


def _quantile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (position - lo) * (ordered[hi] - ordered[lo])


def assess(payload, *, bootstrap_repeats=1000, seed=42):
    if (type(bootstrap_repeats) is not int or not 200 <= bootstrap_repeats <= 10000
            or type(seed) is not int or not 0 <= seed < 2**32):
        return _hold("INVALID_BOOTSTRAP_SETTINGS")
    if (not isinstance(payload, dict) or set(payload) != {"schema", "results", "model_runs"}
            or payload.get("schema") != "football-king-paired-refit-score-v1"):
        return _hold("INVALID_CONTRACT")
    results, runs = payload["results"], payload["model_runs"]
    if (not isinstance(results, list) or not 1 <= len(results) <= 250
            or not isinstance(runs, dict) or set(runs) != set(MODELS)):
        return _hold("INVALID_COHORT")
    try:
        outcomes = {}
        for row in results:
            if not isinstance(row, dict) or set(row) != {
                "fixture_id", "kickoff_utc", "outcome", "result_recorded_utc"
            }:
                raise ValueError("INVALID_RESULT_ROW")
            key = row["fixture_id"]
            if not isinstance(key, str) or not key.strip() or key in outcomes:
                raise ValueError("DUPLICATE_OR_INVALID_FIXTURE")
            if row["outcome"] not in OUTCOMES:
                raise ValueError("INVALID_OUTCOME")
            if not _timestamp(row["kickoff_utc"]) < _timestamp(row["result_recorded_utc"]):
                raise ValueError("INVALID_RESULT_CHRONOLOGY")
            outcomes[key] = row

        aligned = {}
        cutoffs = {}
        for model in MODELS:
            report = runs[model]
            if (not isinstance(report, dict)
                    or report.get("reason") != "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING"
                    or report.get("status") != "HOLD"
                    or report.get("production_recommendations") != "DISABLED"
                    or report.get("positive_ev_verified") is not False
                    or report.get("independent_provenance_verified") is not False
                    or type(report.get("refit_count")) is not int
                    or report["refit_count"] != len(results)
                    or not isinstance(report.get("predictions"), list)
                    or len(report["predictions"]) != len(results)):
                raise ValueError("UNTRUSTED_OR_INCOMPLETE_MODEL_REPORT")
            by_key = {}
            for prediction in report["predictions"]:
                if not isinstance(prediction, dict) or set(prediction) != {
                    "fixture_id", "kickoff_utc", "as_of_utc", "model_id",
                    "training_match_count", "probabilities",
                    "source_authenticity_verified", "independently_timestamped"
                }:
                    raise ValueError("INVALID_PREDICTION_ROW")
                key = prediction["fixture_id"]
                if key not in outcomes or key in by_key:
                    raise ValueError("UNMATCHED_OR_DUPLICATE_PREDICTION")
                if (prediction["kickoff_utc"] != outcomes[key]["kickoff_utc"]
                        or not isinstance(prediction["model_id"], str)
                        or not prediction["model_id"].startswith(
                            "penaltyblog-" + model + "-offline-challenger-")
                        or prediction["source_authenticity_verified"] is not False
                        or prediction["independently_timestamped"] is not False
                        or type(prediction["training_match_count"]) is not int
                        or prediction["training_match_count"] < 30):
                    raise ValueError("UNTRUSTED_PREDICTION")
                cutoff = _timestamp(prediction["as_of_utc"])
                if cutoff >= _timestamp(prediction["kickoff_utc"]):
                    raise ValueError("LOOKAHEAD")
                if key in cutoffs and cutoffs[key] != cutoff:
                    raise ValueError("MODEL_CUTOFF_MISMATCH")
                cutoffs[key] = cutoff
                p = prediction["probabilities"]
                if (not isinstance(p, list) or len(p) != 3
                        or any(type(v) not in (int, float) or not math.isfinite(v)
                               or not 0 <= v <= 1 for v in p)
                        or abs(sum(p) - 1) > 1e-6):
                    raise ValueError("INVALID_PROBABILITIES")
                by_key[key] = p
            if set(by_key) != set(outcomes):
                raise ValueError("UNMATCHED_COHORT")
            aligned[model] = by_key

        ids = sorted(outcomes)
        rows = {model: [
            {"event_id": key, "outcome": outcomes[key]["outcome"],
             "probabilities": dict(zip(OUTCOMES, aligned[model][key]))}
            for key in ids] for model in MODELS}
        metrics = {model: evaluate_1x2(rows[model]) for model in MODELS}
        # All differences are paired on the exact same fixture and result.
        differences = {"log_loss": [], "brier": [], "accuracy": []}
        for key in ids:
            y = OUTCOMES.index(outcomes[key]["outcome"])
            p = aligned["poisson"][key]
            d = aligned["dixon_coles"][key]
            differences["log_loss"].append(
                -math.log(max(p[y], 1e-15)) + math.log(max(d[y], 1e-15)))
            differences["brier"].append(
                sum((p[i] - (i == y))**2 - (d[i] - (i == y))**2 for i in range(3)))
            differences["accuracy"].append(
                int(max(range(3), key=lambda i: d[i]) == y)
                - int(max(range(3), key=lambda i: p[i]) == y))

        intervals = {}
        if len(ids) >= 30:
            rng = random.Random(seed)
            draws = {metric: [] for metric in differences}
            for _ in range(bootstrap_repeats):
                indexes = [rng.randrange(len(ids)) for _ in ids]
                for metric, deltas in differences.items():
                    draws[metric].append(sum(deltas[i] for i in indexes) / len(ids))
            intervals = {metric: [_quantile(draws[metric], .025),
                                  _quantile(draws[metric], .975)]
                         for metric in differences}
        return _hold(
            "UNVERIFIED_PROVENANCE_AND_IID_BOOTSTRAP_LIMITATIONS",
            sample_count=len(ids),
            unverified_diagnostic_metrics=metrics,
            paired_delta_dixon_coles_vs_poisson={
                metric: sum(values) / len(values) for metric, values in differences.items()},
            paired_iid_bootstrap_95pct_intervals=intervals if intervals else None,
            interval_status="COMPUTED_IID_RESEARCH_ONLY" if intervals else "INSUFFICIENT_SAMPLE_N_LT_30",
            bootstrap_repeats=bootstrap_repeats if intervals else 0,
            seed=seed,
            note="IID resampling assumes fixture independence; league/date clustering, selection bias, unverified outcomes and source timestamps remain unresolved.")
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        return _hold(str(exc))
