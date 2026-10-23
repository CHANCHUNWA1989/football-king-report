"""Fail-closed pinned-source walk-forward research pipeline.

Only an externally supplied trusted digest may admit a history file.
The output remains research-only even when all mechanical checks pass.
"""
from offline_history_source_gate import load_pinned_history
from offline_walkforward import evaluate_walkforward


def replay_pinned_walkforward(path, *, expected_sha256, expected_model_version,
                              min_train=60, test_size=30, step_size=30,
                              embargo_hours=24):
    hold = {"status": "HOLD", "reason": "PINNED_WALKFORWARD_NOT_ADMITTED",
            "production_recommendations": "DISABLED"}
    source = load_pinned_history(
        path, expected_sha256=expected_sha256,
        expected_model_version=expected_model_version)
    if source["status"] != "RESEARCH_ONLY":
        return {**hold, "source_reason": source["reason"]}
    report = evaluate_walkforward(
        source["rows"], min_train=min_train, test_size=test_size,
        step_size=step_size, embargo_hours=embargo_hours)
    if report["status"] != "RESEARCH_ONLY":
        return {**hold, "evaluation_reason": report["reason"]}
    return {**report, "reason": "PINNED_SOURCE_WALKFORWARD_DIAGNOSTIC",
            "source_sha256": source["sha256"],
            "source_model_version": source["model_version"],
            "source_row_count": source["row_count"],
            "external_timestamp_verified": False,
            "source_authenticity_verified": False,
            "production_recommendations": "DISABLED"}
