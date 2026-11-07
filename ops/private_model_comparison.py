"""Paired, private, offline Poisson vs Dixon-Coles comparison.

Only compare exactly the same fixture cohort and outcomes. No promotion.
"""
from ops.private_offline_scoring import score


def compare(poisson_rows, dixon_coles_rows):
    if not isinstance(poisson_rows, list) or not isinstance(dixon_coles_rows, list):
        raise ValueError("INVALID_MODEL_COHORT")
    def keyed(rows):
        result = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("fixture_id"), str):
                raise ValueError("INVALID_MODEL_ROW")
            key = row["fixture_id"]
            if key in result:
                raise ValueError("DUPLICATE_MODEL_FIXTURE")
            result[key] = row
        return result
    a, b = keyed(poisson_rows), keyed(dixon_coles_rows)
    if not a or a.keys() != b.keys():
        raise ValueError("UNPAIRED_MODEL_COHORT")
    for key in a:
        for field in ("outcome", "prediction_utc", "kickoff_utc", "result_recorded_utc"):
            if a[key].get(field) != b[key].get(field):
                raise ValueError("INCONSISTENT_MODEL_TARGET_OR_RESULT")
    left, right = score(poisson_rows), score(dixon_coles_rows)
    return {
        "status": "RESEARCH_ONLY",
        "production_recommendations": "DISABLED",
        "positive_ev_verified": False,
        "independent_provenance_verified": False,
        "model_promoted": False,
        "paired_fixture_count": len(a),
        "poisson": {k: left[k] for k in ("log_loss", "multiclass_brier_score", "calibration")},
        "dixon_coles": {k: right[k] for k in ("log_loss", "multiclass_brier_score", "calibration")},
        "log_loss_delta_dc_minus_poisson": round(right["log_loss"] - left["log_loss"], 6),
        "brier_delta_dc_minus_poisson": round(right["multiclass_brier_score"] - left["multiclass_brier_score"], 6),
        "note": "Negative deltas favor Dixon-Coles on this unverified retrospective cohort only."
    }
