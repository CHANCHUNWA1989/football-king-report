"""Bridge two real penaltyblog refit reports into paired retrospective diagnostics.

Only reports from existing refit_walkforward contract are accepted. No claims
of independent timestamps, source authenticity, or verified bookmaker EV.
"""
from ops.private_soccerdata_baseline_comparison import compare_to_frequency_baseline


def compare_refit_reports_to_baseline(records, poisson_report, dixon_coles_report,
                                      *, min_train=30, test_days=7):
    def extract(report, model):
        if (not isinstance(report, dict) or report.get("status") != "HOLD"
                or report.get("reason") != "PROSPECTIVE_SOURCE_AND_RESULT_ATTESTATION_MISSING"
                or report.get("production_recommendations") != "DISABLED"
                or report.get("independent_provenance_verified") is not False
                or report.get("positive_ev_verified") is not False
                or report.get("refit_count") != len(report.get("predictions", []))):
            raise ValueError("UNTRUSTED_REFIT_REPORT")
        predictions = report["predictions"]
        if not isinstance(predictions, list) or not predictions:
            raise ValueError("EMPTY_REFIT_REPORT")
        result = {}
        for p in predictions:
            if (not isinstance(p, dict) or set(p) != {
                    "fixture_id", "kickoff_utc", "as_of_utc", "model_id",
                    "training_match_count", "probabilities",
                    "source_authenticity_verified", "independently_timestamped"}
                    or p["source_authenticity_verified"] is not False
                    or p["independently_timestamped"] is not False
                    or not isinstance(p["model_id"], str)
                    or not p["model_id"].startswith("penaltyblog-" + model)
                    or type(p["training_match_count"]) is not int
                    or p["training_match_count"] < 30):
                raise ValueError("INVALID_REFIT_PREDICTION")
            key = p["fixture_id"]
            probs = p["probabilities"]
            if not isinstance(key, str) or not key or key in result or not isinstance(probs, list) or len(probs) != 3:
                raise ValueError("INVALID_REFIT_FIXTURE")
            result[key] = dict(zip(("H", "D", "A"), probs))
        return result
    a = extract(poisson_report, "poisson")
    b = extract(dixon_coles_report, "dixon_coles")
    if set(a) != set(b):
        raise ValueError("UNPAIRED_REFIT_MODELS")
    outcomes = {r["source_index"]: r["outcome"] for r in records}
    if len(outcomes) != len(records):
        raise ValueError("DUPLICATE_HISTORY_ID")
    if not set(a).issubset(outcomes):
        raise ValueError("REFIT_HISTORY_ID_MISMATCH")
    def rows(probabilities):
        return [{"fixture_id": k, "outcome": outcomes[k], "probabilities": v}
                for k, v in probabilities.items()]
    left = compare_to_frequency_baseline(records, rows(a), min_train=min_train, test_days=test_days)
    right = compare_to_frequency_baseline(records, rows(b), min_train=min_train, test_days=test_days)
    if left.get("status") != "RESEARCH_ONLY" or right.get("status") != "RESEARCH_ONLY":
        return {"status": "HOLD", "reason": "INSUFFICIENT_HOLDOUT",
                "production_recommendations": "DISABLED"}
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "fixture_count": left["fixture_count"], "baseline": left["baseline"],
            "poisson": left["challenger"], "dixon_coles": right["challenger"],
            "poisson_minus_baseline_log_loss": left["log_loss_delta_challenger_minus_baseline"],
            "dixon_coles_minus_baseline_log_loss": right["log_loss_delta_challenger_minus_baseline"],
            "positive_ev_verified": False, "independent_provenance_verified": False,
            "model_promoted": False,
            "note": "Reports are caller supplied and not independently attested; no production model selection."}
