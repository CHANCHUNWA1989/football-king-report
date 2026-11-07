"""Three-way identical-holdout offline comparison for historical CSV cohorts.

Dixon-Coles here is an approximate low-score correction, not full joint MLE.
All input history is retrospective and lacks independently verified availability.
"""
import argparse
import json
import sys
from ops.private_soccerdata_csv_research import import_settled_csv
from ops.private_soccerdata_team_poisson import evaluate_team_poisson
from ops.private_soccerdata_dc_research import evaluate_dixon_coles_correction
from ops.private_soccerdata_baseline_comparison import compare_to_frequency_baseline
from ops.private_soccerdata_research_manifest import build_research_manifest


def compare_three_models_csv(path, *, min_train=30, test_days=7):
    payload = import_settled_csv(path, min_train=min_train, test_days=test_days)
    records = payload["records"]
    poisson = evaluate_team_poisson(records, min_train=min_train, test_days=test_days)
    dc = evaluate_dixon_coles_correction(records, min_train=min_train, test_days=test_days)
    if poisson["status"] != "RESEARCH_ONLY" or dc["status"] != "RESEARCH_ONLY":
        return {"status": "HOLD", "reason": "INSUFFICIENT_HOLDOUT",
                "production_recommendations": "DISABLED", "model_promoted": False}
    def compare(model):
        rows = [{"fixture_id": p["fixture_id"], "outcome": p["outcome"],
                 "probabilities": p["probabilities"]} for p in model["predictions"]]
        return compare_to_frequency_baseline(records, rows, min_train=min_train,
                                             test_days=test_days)
    a, b = compare(poisson), compare(dc)
    if (a["status"] != "RESEARCH_ONLY" or b["status"] != "RESEARCH_ONLY"
            or a["fixture_count"] != b["fixture_count"]
            or a["fixture_count"] != poisson["prediction_count"]
            or b["fixture_count"] != dc["prediction_count"]):
        raise ValueError("THREE_WAY_COHORT_MISMATCH")
    if ({p["fixture_id"] for p in poisson["predictions"]} !=
            {p["fixture_id"] for p in dc["predictions"]}):
        raise ValueError("THREE_WAY_FIXTURE_MISMATCH")
    return {"schema": "football-king-three-model-csv-research-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "fixture_count": a["fixture_count"], "fold_count": a["fold_count"],
            "manifest": build_research_manifest(records, min_train=min_train,
                                                 test_days=test_days),
            "frequency_baseline": a["baseline"],
            "fitted_team_poisson": a["challenger"],
            "approximate_dixon_coles": b["challenger"],
            "poisson_minus_baseline_log_loss": a["log_loss_delta_challenger_minus_baseline"],
            "dc_minus_baseline_log_loss": b["log_loss_delta_challenger_minus_baseline"],
            "poisson_minus_baseline_brier": a["brier_delta_challenger_minus_baseline"],
            "dc_minus_baseline_brier": b["brier_delta_challenger_minus_baseline"],
            "independent_provenance_verified": False, "positive_ev_verified": False,
            "model_promoted": False,
            "limitations": "No independently verified forecast availability, odds or positive EV. DC is approximate, not joint MLE."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output")
    parser.add_argument("--min-train", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        report = compare_three_models_csv(args.csv, min_train=args.min_train,
                                          test_days=args.test_days)
        output = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2,
                            allow_nan=False) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
        else:
            sys.stdout.write(output)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"THREE_MODEL_RESEARCH_REJECTED: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
