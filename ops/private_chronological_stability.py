"""Chronological paired model stability diagnostics, research only.

Splits fixtures by kickoff order, never by outcome or model performance.
"""
from datetime import datetime
from ops.private_model_comparison import compare


def _timestamp(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_KICKOFF")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_KICKOFF") from exc
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_KICKOFF")
    return parsed


def evaluate(poisson_rows, dixon_coles_rows, *, min_segment=30):
    if type(min_segment) is not int or min_segment < 2:
        raise ValueError("INVALID_MIN_SEGMENT")
    # First validate complete cohort parity and all chronology before splitting.
    overall = compare(poisson_rows, dixon_coles_rows)
    ordered = sorted(poisson_rows, key=lambda r: (_timestamp(r["kickoff_utc"]), r["fixture_id"]))
    midpoint = len(ordered) // 2
    if midpoint < min_segment or len(ordered) - midpoint < min_segment:
        return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
                "positive_ev_verified": False, "model_promoted": False,
                "paired_fixture_count": len(ordered), "segment_status": "INSUFFICIENT_CHRONOLOGICAL_SEGMENTS",
                "minimum_per_segment": min_segment, "overall": overall,
                "segments": []}
    dc = {row["fixture_id"]: row for row in dixon_coles_rows}
    segments = []
    for name, cohort in (("earlier", ordered[:midpoint]), ("later", ordered[midpoint:])):
        report = compare(cohort, [dc[row["fixture_id"]] for row in cohort])
        segments.append({"period": name, "paired_fixture_count": len(cohort),
                         "log_loss_delta_dc_minus_poisson": report["log_loss_delta_dc_minus_poisson"],
                         "brier_delta_dc_minus_poisson": report["brier_delta_dc_minus_poisson"],
                         "evidence_status": report["evidence_status"]})
    first, second = (x["log_loss_delta_dc_minus_poisson"] for x in segments)
    direction_consistent = (first > 0 and second > 0) or (first < 0 and second < 0)
    return {"status": "RESEARCH_ONLY", "production_recommendations": "DISABLED",
            "positive_ev_verified": False, "model_promoted": False,
            "paired_fixture_count": len(ordered), "segment_status": "DESCRIPTIVE_ONLY",
            "minimum_per_segment": min_segment, "direction_consistent": direction_consistent,
            "overall": overall, "segments": segments}
