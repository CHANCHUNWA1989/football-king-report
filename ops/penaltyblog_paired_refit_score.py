"""Strictly paired Poisson / Dixon-Coles offline forecast scoring.

Scores are diagnostic only: neither source authenticity nor prospective
timestamp nor independently confirmed final results are established here.
"""
import argparse
import json
from .offline_1x2_validation import evaluate_1x2
from .penaltyblog_research_bridge import _timestamp

NAMES = ("poisson", "dixon_coles")
OUTCOMES = ("H", "D", "A")


def _hold(reason, **extra):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED", "positive_ev_verified": False,
            "model_promoted": False, "independent_provenance_verified": False,
            **extra}


def score_paired(payload):
    if not isinstance(payload, dict) or set(payload) != {"schema", "results", "model_runs"}:
        return _hold("INVALID_CONTRACT")
    if payload["schema"] != "football-king-paired-refit-score-v1":
        return _hold("INVALID_CONTRACT")
    runs = payload["model_runs"]
    if not isinstance(runs, dict) or set(runs) != set(NAMES):
        return _hold("MISSING_MODEL_RUN")
    results = payload["results"]
    if not isinstance(results, list) or not 1 <= len(results) <= 250:
        return _hold("INVALID_RESULTS")
    try:
        expected = {}
        for row in results:
            if not isinstance(row, dict) or set(row) != {
                "fixture_id", "kickoff_utc", "outcome", "result_recorded_utc"
            }:
                raise ValueError("INVALID_RESULT_ROW")
            key = row["fixture_id"]
            if not isinstance(key, str) or not key.strip() or key in expected:
                raise ValueError("DUPLICATE_OR_INVALID_FIXTURE")
            if row["outcome"] not in OUTCOMES:
                raise ValueError("INVALID_OUTCOME")
            if not _timestamp(row["kickoff_utc"]) < _timestamp(row["result_recorded_utc"]):
                raise ValueError("INVALID_RESULT_CHRONOLOGY")
            expected[key] = row
        metrics = {}
        as_of_by_fixture = {}
        for model in NAMES:
            report = runs[model]
            if (not isinstance(report, dict) or report.get("status") != "HOLD"
                    or report.get("reason") != "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING"
                    or report.get("production_recommendations") != "DISABLED"
                    or report.get("positive_ev_verified") is not False
                    or report.get("independent_provenance_verified") is not False
                    or report.get("refit_count") != len(results)
                    or not isinstance(report.get("predictions"), list)):
                raise ValueError("INVALID_OR_UNTRUSTED_MODEL_REPORT")
            predictions = report["predictions"]
            if len(predictions) != len(results):
                raise ValueError("MISSING_OR_EXTRA_PREDICTION")
            rows = []
            seen = set()
            for p in predictions:
                if not isinstance(p, dict) or set(p) != {
                    "fixture_id", "kickoff_utc", "as_of_utc", "model_id",
                    "training_match_count", "probabilities",
                    "source_authenticity_verified", "independently_timestamped"
                }:
                    raise ValueError("INVALID_PREDICTION_ROW")
                key = p["fixture_id"]
                if not isinstance(key, str) or key not in expected or key in seen:
                    raise ValueError("MISSING_EXTRA_OR_DUPLICATE_FIXTURE")
                seen.add(key)
                if not isinstance(p["model_id"], str) or not p["model_id"].startswith(
                        "penaltyblog-" + model + "-offline-challenger-"):
                    raise ValueError("MODEL_ID_MISMATCH")
                if p["source_authenticity_verified"] is not False or p["independently_timestamped"] is not False:
                    raise ValueError("UNTRUSTED_PROVENANCE_CLAIM")
                if type(p["training_match_count"]) is not int or p["training_match_count"] < 30:
                    raise ValueError("INVALID_TRAINING_COUNT")
                if p["kickoff_utc"] != expected[key]["kickoff_utc"]:
                    raise ValueError("KICKOFF_MISMATCH")
                if not _timestamp(p["as_of_utc"]) < _timestamp(p["kickoff_utc"]):
                    raise ValueError("LOOKAHEAD")
                cutoff = _timestamp(p["as_of_utc"])
                if key in as_of_by_fixture and as_of_by_fixture[key] != cutoff:
                    raise ValueError("MODEL_CUTOFF_MISMATCH")
                as_of_by_fixture[key] = cutoff
                probabilities = p["probabilities"]
                if not isinstance(probabilities, list) or len(probabilities) != 3:
                    raise ValueError("INVALID_PROBABILITIES")
                rows.append({
                    "event_id": key, "outcome": expected[key]["outcome"],
                    "probabilities": dict(zip(OUTCOMES, probabilities))
                })
            if seen != set(expected):
                raise ValueError("UNMATCHED_COHORT")
            metrics[model] = evaluate_1x2(rows)
        return _hold("UNVERIFIED_RESULT_SOURCE_AND_FORECAST_PROVENANCE",
                     paired_fixture_count=len(results),
                     unverified_diagnostic_metrics=metrics,
                     note="Both models scored on identical fixture IDs and cutoffs. No external result/timestamp evidence, odds, EV or ROI.")
    except (ValueError, KeyError, TypeError, OverflowError, AttributeError) as exc:
        return _hold(str(exc))


def _unique_pairs(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise ValueError("DUPLICATE_JSON_KEY")
        d[k] = v
    return d


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh, object_pairs_hook=_unique_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    print(json.dumps(score_paired(data), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
