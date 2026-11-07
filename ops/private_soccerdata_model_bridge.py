"""Strict soccerdata outcome-to-forecast joining; never synthesize kickoff UTC.

Upstream MatchHistory contains settled results, not independently sealed
pre-match predictions. Only join to independently supplied forecast rows.
"""
from ops.private_model_comparison import compare


def join_outcomes_and_compare(history, poisson_rows, dixon_coles_rows):
    if not isinstance(history, dict) or history.get("provider") != "soccerdata.MatchHistory" or history.get("point_in_time_backtest_ready") is not False:
        raise ValueError("UNTRUSTED_HISTORY_ENVELOPE")
    records = history.get("records")
    if not isinstance(records, list) or not records or history.get("count") != len(records):
        raise ValueError("INVALID_HISTORY_RECORDS")
    if not isinstance(poisson_rows, list) or not isinstance(dixon_coles_rows, list):
        raise ValueError("INVALID_FORECAST_ROWS")
    by_id = {}
    for record in records:
        if not isinstance(record, dict) or record.get("source") != "soccerdata.MatchHistory" or record.get("kickoff_time_verified") is not False or record.get("odds_capture_verified") is not False or record.get("pre_match_features_verified") is not False:
            raise ValueError("HISTORY_PROVENANCE_INCONSISTENT")
        key = record.get("source_index")
        if not isinstance(key, str) or not key or key in by_id or record.get("outcome") not in ("H", "D", "A"):
            raise ValueError("INVALID_HISTORY_ID_OR_RESULT")
        by_id[key] = record["outcome"]
    if not poisson_rows or len(poisson_rows) != len(by_id) or len(dixon_coles_rows) != len(by_id):
        raise ValueError("INCOMPLETE_HISTORICAL_COHORT")
    for rows in (poisson_rows, dixon_coles_rows):
        ids = [r.get("fixture_id") if isinstance(r, dict) else None for r in rows]
        if set(ids) != set(by_id) or len(ids) != len(set(ids)):
            raise ValueError("HISTORICAL_FIXTURE_MISMATCH")
        for row in rows:
            if row.get("outcome") != by_id[row["fixture_id"]]:
                raise ValueError("FORECAST_RESULT_DISAGREEMENT")
    report = compare(poisson_rows, dixon_coles_rows)
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "model_promoted": False,
            "historical_outcomes_joined": len(by_id),
            "historical_source": "soccerdata.MatchHistory",
            "pre_match_provenance_independently_verified": False,
            "odds_capture_verified": False,
            "comparison": report}
