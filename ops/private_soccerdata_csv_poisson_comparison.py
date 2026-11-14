"""Run paired frequency-versus-fitted-Poisson offline CSV research.

The same chronological holdout fixtures and actual outcomes are used for both.
No external download, timestamp attestation, bookmaker prices or EV claims.
"""
import argparse
import json
import sys
from ops.private_soccerdata_csv_research import import_settled_csv
from ops.private_soccerdata_team_poisson import evaluate_team_poisson
from ops.private_soccerdata_baseline_comparison import compare_to_frequency_baseline
from ops.private_soccerdata_research_manifest import build_research_manifest


def run_csv_poisson_comparison(path, *, min_train=30, test_days=7):
    payload = import_settled_csv(path, min_train=min_train, test_days=test_days)
    records = payload["records"]
    poisson = evaluate_team_poisson(records, min_train=min_train, test_days=test_days)
    if poisson["status"] != "RESEARCH_ONLY":
        return {"status": "HOLD", "reason": "INSUFFICIENT_HOLDOUT",
                "production_recommendations": "DISABLED", "model_promoted": False}
    challenger = [{"fixture_id": p["fixture_id"], "outcome": p["outcome"],
                   "probabilities": p["probabilities"]}
                  for p in poisson["predictions"]]
    paired = compare_to_frequency_baseline(records, challenger, min_train=min_train,
                                            test_days=test_days)
    if paired["status"] != "RESEARCH_ONLY" or paired["fixture_count"] != poisson["prediction_count"]:
        raise ValueError("POISSON_BASELINE_HOLDOUT_MISMATCH")
    if (abs(paired["challenger"]["log_loss"] - poisson["log_loss"]) > 1e-6
            or abs(paired["challenger"]["multiclass_brier_score"] -
                   poisson["multiclass_brier_score"]) > 1e-6):
        raise ValueError("POISSON_SCORE_MISMATCH")
    return {"schema": "football-king-csv-poisson-comparison-v1",
            "status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "manifest": build_research_manifest(records, min_train=min_train,
                                                 test_days=test_days),
            "fixture_count": paired["fixture_count"], "fold_count": paired["fold_count"],
            "frequency_baseline": paired["baseline"],
            "fitted_team_poisson": paired["challenger"],
            "poisson_minus_baseline_log_loss": paired["log_loss_delta_challenger_minus_baseline"],
            "poisson_minus_baseline_brier": paired["brier_delta_challenger_minus_baseline"],
            "independent_provenance_verified": False, "positive_ev_verified": False,
            "model_promoted": False,
            "limitations": "Retrospective calendar-day holdout; no verified pre-match source availability or odds."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--output")
    parser.add_argument("--min-train", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=7)
    args = parser.parse_args(argv)
    try:
        report = run_csv_poisson_comparison(args.csv, min_train=args.min_train,
                                            test_days=args.test_days)
        rendered = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2,
                              allow_nan=False) + "\n"
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"POISSON_RESEARCH_REJECTED: {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
