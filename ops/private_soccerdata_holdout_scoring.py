"""Score only held-out soccerdata walk-forward fixtures, research only.

Inputs must be independently supplied paired forecasts, not in-sample model
outputs. Calendar-day folds do not authenticate historical data provenance.
"""
from ops.private_model_comparison import compare


def score_holdout_folds(fold_report, poisson_rows, dixon_coles_rows):
    if (not isinstance(fold_report, dict) or fold_report.get("status") != "RESEARCH_ONLY"
            or fold_report.get("production_recommendations") != "DISABLED"
            or fold_report.get("models_fitted") is not False
            or fold_report.get("point_in_time_backtest_ready") is not False):
        raise ValueError("UNTRUSTED_FOLD_REPORT")
    folds = fold_report.get("folds")
    if not isinstance(folds, list) or not folds or fold_report.get("fold_count") != len(folds):
        raise ValueError("NO_VALID_HOLDOUT_FOLDS")
    if not isinstance(poisson_rows, list) or not isinstance(dixon_coles_rows, list):
        raise ValueError("INVALID_FORECAST_COHORT")
    expected, previously_tested = set(), set()
    for fold in folds:
        if not isinstance(fold, dict) or set(fold) != {
                "train_ids", "test_ids", "train_last_local_day", "test_first_local_day"}:
            raise ValueError("INVALID_FOLD")
        train, test = fold["train_ids"], fold["test_ids"]
        if (not isinstance(train, list) or not isinstance(test, list) or not train or not test
                or any(not isinstance(k, str) or not k for k in train + test)
                or len(set(train)) != len(train) or len(set(test)) != len(test)
                or not set(train).isdisjoint(test)
                or not previously_tested.isdisjoint(test)
                or not isinstance(fold["train_last_local_day"], str)
                or not isinstance(fold["test_first_local_day"], str)
                or fold["train_last_local_day"] >= fold["test_first_local_day"]):
            raise ValueError("TRAIN_TEST_LEAKAGE")
        expected.update(test)
        previously_tested.update(test)
    if not expected:
        raise ValueError("EMPTY_HOLDOUT")
    for rows in (poisson_rows, dixon_coles_rows):
        ids = [r.get("fixture_id") if isinstance(r, dict) else None for r in rows]
        if len(ids) != len(expected) or set(ids) != expected:
            raise ValueError("FORECAST_HOLDOUT_MISMATCH")
    result = compare(poisson_rows, dixon_coles_rows)
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "holdout_fixture_count": len(expected), "fold_count": len(folds),
            "model_promoted": False, "positive_ev_verified": False,
            "independent_provenance_verified": False,
            "comparison": result,
            "note": "Scoring is descriptive; supplied predictions and data availability remain unauthenticated."}
