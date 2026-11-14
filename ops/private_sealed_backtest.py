"""Join sealed private prematch forecasts with separately supplied results.

Local hash verification is not independent proof of historic capture or outcomes.
"""
from ops.private_forecast_snapshot import verify
from ops.private_chronological_stability import evaluate


def evaluate_sealed(poisson_snapshots, dixon_coles_snapshots, results, *, min_segment=30):
    if not all(isinstance(x, list) for x in (poisson_snapshots, dixon_coles_snapshots, results)):
        raise ValueError("INVALID_SEALED_COHORT")
    if not results:
        raise ValueError("EMPTY_RESULTS")
    outcomes = {}
    for row in results:
        if not isinstance(row, dict) or set(row) != {"fixture_id", "kickoff_utc", "outcome", "result_recorded_utc"}:
            raise ValueError("INVALID_RESULT_FIELDS")
        fixture = row["fixture_id"]
        if not isinstance(fixture, str) or not fixture or fixture in outcomes or row["outcome"] not in ("H", "D", "A"):
            raise ValueError("INVALID_OR_DUPLICATE_RESULT")
        outcomes[fixture] = row

    def rows(snapshots, expected_model):
        seen = set()
        paired = []
        for snapshot in snapshots:
            verify(snapshot)
            forecast = snapshot["forecast"]
            fixture = forecast["fixture_id"]
            if forecast["model"] != expected_model or fixture in seen or fixture not in outcomes:
                raise ValueError("INVALID_MODEL_OR_UNMATCHED_FIXTURE")
            seen.add(fixture)
            result = outcomes[fixture]
            if forecast["kickoff_utc"] != result["kickoff_utc"]:
                raise ValueError("KICKOFF_MISMATCH")
            paired.append({"fixture_id": fixture,
                           "probabilities": forecast["probabilities"],
                           "outcome": result["outcome"],
                           "prediction_utc": forecast["prediction_utc"],
                           "kickoff_utc": forecast["kickoff_utc"],
                           "result_recorded_utc": result["result_recorded_utc"]})
        if seen != outcomes.keys():
            raise ValueError("UNPAIRED_RESULT_COHORT")
        return paired

    left = rows(poisson_snapshots, "poisson")
    right = rows(dixon_coles_snapshots, "dixon_coles")
    report = evaluate(left, right, min_segment=min_segment)
    report["source_capture_independently_attested"] = False
    report["result_provenance_verified"] = False
    report["production_recommendations"] = "DISABLED"
    report["positive_ev_verified"] = False
    report["model_promoted"] = False
    return report
