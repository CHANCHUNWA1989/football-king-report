"""Single-entry offline Poisson/DC refit -> paired scoring research pipeline.

All data and result labels are caller supplied and not independently attested.
No online collection, betting recommendations, model promotion or EV claims.
"""
import argparse
import json
from .penaltyblog_walkforward_refit import refit_walkforward
from .penaltyblog_paired_refit_score import score_paired
from .penaltyblog_research_bridge import _timestamp


def _hold(reason, **extra):
    return {"status": "HOLD", "reason": reason,
            "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "model_promoted": False,
            "independent_provenance_verified": False, **extra}


def run_pipeline(payload, *, model_factories=None):
    if (not isinstance(payload, dict)
            or set(payload) != {"schema", "production_recommendations",
                                "historical_matches", "targets", "results", "min_training"}
            or payload.get("schema") != "football-king-two-model-pipeline-v1"
            or payload.get("production_recommendations") != "DISABLED"):
        return _hold("INVALID_CONTRACT")
    targets, results = payload["targets"], payload["results"]
    if not isinstance(targets, list) or not isinstance(results, list) or not targets:
        return _hold("INVALID_COHORT")
    try:
        target_keys = set()
        target_times = {}
        for t in targets:
            if not isinstance(t, dict) or not isinstance(t.get("event_id"), str):
                raise ValueError("INVALID_TARGET")
            key = t["event_id"]
            if not key or key in target_keys:
                raise ValueError("DUPLICATE_TARGET")
            target_keys.add(key)
            target_times[key] = _timestamp(t["kickoff_utc"])
        result_keys = set()
        for r in results:
            if not isinstance(r, dict) or not isinstance(r.get("fixture_id"), str):
                raise ValueError("INVALID_RESULT")
            key = r["fixture_id"]
            if key in result_keys:
                raise ValueError("DUPLICATE_RESULT")
            result_keys.add(key)
        if result_keys != target_keys:
            raise ValueError("TARGET_RESULT_COHORT_MISMATCH")
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        return _hold(str(exc))

    runs = {}
    for model in ("poisson", "dixon_coles"):
        params = {
            "schema": "football-king-penaltyblog-walkforward-v1",
            "production_recommendations": "DISABLED",
            "model": model,
            "historical_matches": payload["historical_matches"],
            "targets": targets,
            "min_training": payload["min_training"],
        }
        factory = model_factories.get(model) if model_factories is not None else None
        report = refit_walkforward(params, model_factory=factory)
        if report.get("reason") != "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING":
            return _hold("MODEL_REFIT_BLOCKED", blocked_model=model,
                         model_reason=report.get("reason"))
        runs[model] = report
    paired = score_paired({
        "schema": "football-king-paired-refit-score-v1",
        "results": results,
        "model_runs": runs,
    })
    if "unverified_diagnostic_metrics" not in paired:
        return _hold("PAIRED_SCORE_BLOCKED", paired_reason=paired.get("reason"))
    return _hold("UNVERIFIED_SOURCE_AND_PROSPECTIVE_ATTESTATION",
                 paired_fixture_count=paired["paired_fixture_count"],
                 model_refit_counts={name: runs[name]["refit_count"] for name in runs},
                 unverified_diagnostic_metrics=paired["unverified_diagnostic_metrics"],
                 paired_forecast_cutoffs_verified_locally=True,
                 note="Pipeline refits both models for each target; all outcomes and timestamps remain unverified caller inputs.")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as fh:
        payload = json.load(fh, object_pairs_hook=_unique_pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")))
    print(json.dumps(run_pipeline(payload), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
