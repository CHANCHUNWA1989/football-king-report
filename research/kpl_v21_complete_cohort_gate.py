"""KPL V21 strict *reporting* gate for a prospective shadow BO7 cohort.

This module intentionally suppresses model scores from selected easy/finished
series when any registered series is unresolved, any played map has no decision,
any result is UNVERIFIED, or a recorded decision is outside played slots.
No source claims or local hashes are independently authenticated.

An internal diagnostic pass is NOT verified KPL forecasting skill, source
authority, legitimate use rights, or permission to offer a wager.
"""
from __future__ import annotations

from pathlib import Path

from research.kpl_v20_shadow_trial import (
    MAX_SERIES, _load_manifest, _read_decision, _utcnow, _validate_outcomes,
    audit_shadow_trial,
)

MAX_MAPS = MAX_SERIES * 7


def _hold(reasons, *, counts=None, metrics=None, eligible=False):
    c = counts or {}
    return {
        "status": "HOLD",
        "reasons": list(dict.fromkeys(reasons)),
        "registered_series_count": c.get("registered_series_count", 0),
        "completed_series_count": c.get("completed_series_count", 0),
        "unresolved_registered_series_count": c.get(
            "unresolved_registered_series_count", 0),
        "observed_result_maps": c.get("observed_result_maps", 0),
        "played_maps": c.get("played_maps", 0),
        "missing_pregame_decision_count": c.get(
            "missing_pregame_decision_count", 0),
        "forecast_decision_count": c.get("forecast_decision_count", 0),
        "hold_decision_count": c.get("hold_decision_count", 0),
        "unverified_result_maps": c.get("unverified_result_maps", 0),
        "extra_recorded_decision_count": c.get("extra_recorded_decision_count", 0),
        "played_map_decision_coverage": c.get(
            "played_map_decision_coverage"),
        "played_map_forecast_coverage": c.get(
            "played_map_forecast_coverage"),
        "cohort_all_registered_series_complete": c.get(
            "cohort_all_registered_series_complete", False),
        "all_played_map_decisions_present": c.get(
            "all_played_map_decisions_present", False),
        "all_result_sources_claimed": c.get("all_result_sources_claimed", False),
        "minimum_research_sample_met": c.get("minimum_research_sample_met", False),
        "internal_diagnostic_cohort_gate_passed": bool(eligible),
        "diagnostic_only_not_real_kpl": metrics if eligible else None,
        "diagnostic_scores_suppressed": not eligible,
        "trial_registration_independently_witnessed": False,
        "decisions_independently_witnessed": False,
        "results_independently_authenticated": False,
        "schedule_independently_authenticated": False,
        "source_usage_rights_independently_verified": False,
        "real_kpl_accuracy_verified": False,
        "positive_ev_verified": False,
        "research_only": True,
        "live_execution_allowed": False,
        "production_recommendations": "DISABLED",
    }


def audit_complete_cohort(trial_dir, outcomes, *, min_completed_series=40,
                          min_forecast_maps=120):
    """All-or-none internal cohort quality gate with full-universe coverage.

    Only a complete, locally consistent cohort with source-*asserted* results,
    no missing decision and no extra/out-of-sample decision can display *internal*
    diagnostics. More stringent requirements to claim real calibration are
    external, and this function will NEVER assert those are satisfied.

    This is an evaluation-time audit only; local filesystem/time can be forged.
    """
    if (type(min_completed_series) is not int or
            not 1 <= min_completed_series <= MAX_SERIES or
            type(min_forecast_maps) is not int or
            not 1 <= min_forecast_maps <= MAX_MAPS):
        return _hold(["INVALID_SHADOW_GATE_POLICY"])

    try:
        base = audit_shadow_trial(trial_dir, outcomes)
        manifest, fingerprint = _load_manifest(trial_dir)
        grouped, completed = _validate_outcomes(outcomes, manifest, _utcnow())
        played_slots = {
            (sid, r["game_number"])
            for sid, rows in grouped.items()
            for r in rows
        }
        count_unverified = sum(
            r["source_status"] != "SOURCE_ASSERTED"
            for rows in grouped.values() for r in rows)
        recorded_slots = set()
        for path in (Path(trial_dir) / "decisions").iterdir():
            record, _ = _read_decision(path, fingerprint)
            decision = record["decision"]
            recorded_slots.add((decision["series_id"], decision["game_number"]))
        count_missing = len(played_slots - recorded_slots)
        count_extra = len(recorded_slots - played_slots)
        all_completed = (len(completed) == len(manifest["series"]))
        all_present = count_missing == 0 and count_extra == 0
        all_claimed = bool(played_slots) and count_unverified == 0
        sample_met = (
            len(completed) >= min_completed_series and
            base["forecast_decision_count"] >= min_forecast_maps)
        coverage = (base["forecast_decision_count"] /
                    len(played_slots) if played_slots else None)
        decision_coverage = (
            (base["forecast_decision_count"] + base["hold_decision_count"]) /
            len(played_slots) if played_slots else None)
        counts = {
            "registered_series_count": len(manifest["series"]),
            "completed_series_count": len(completed),
            "unresolved_registered_series_count": (
                len(manifest["series"]) - len(completed)),
            "observed_result_maps": len(played_slots),
            "played_maps": len(played_slots),
            "missing_pregame_decision_count": count_missing,
            "forecast_decision_count": base["forecast_decision_count"],
            "hold_decision_count": base["hold_decision_count"],
            "unverified_result_maps": count_unverified,
            "extra_recorded_decision_count": count_extra,
            "played_map_decision_coverage": decision_coverage,
            "played_map_forecast_coverage": coverage,
            "cohort_all_registered_series_complete": all_completed,
            "all_played_map_decisions_present": all_present,
            "all_result_sources_claimed": all_claimed,
            "minimum_research_sample_met": sample_met,
        }
        reasons = []
        if not all_completed:
            reasons.append("REGISTERED_SERIES_UNRESOLVED")
        if count_missing:
            reasons.append("MISSING_PRE_GAME_DECISIONS")
        if count_extra:
            reasons.append("UNSETTLED_OR_ORPHAN_RECORDED_DECISIONS")
        if not all_claimed:
            reasons.append("UNVERIFIED_RESULT_IN_REGISTERED_COHORT")
        if not sample_met:
            reasons.append("MINIMUM_COHORT_SAMPLE_NOT_MET")
        if not base["diagnostic_only_not_real_kpl"] and not reasons:
            reasons.append("NO_COMPARABLE_RESEARCH_FORECASTS")
        eligible = (
            not reasons and base["diagnostic_only_not_real_kpl"] is not None)
        reasons.extend([
            "LOCAL_CLOCK_AND_RECORDS_NOT_INDEPENDENTLY_WITNESSED",
            "OFFICIAL_RESULTS_AND_USAGE_RIGHTS_NOT_INDEPENDENTLY_VERIFIED",
            "REAL_KPL_MODEL_CALIBRATION_NOT_VERIFIED",
        ])
        return _hold(
            reasons, counts=counts, eligible=eligible,
            metrics=base["diagnostic_only_not_real_kpl"])
    except (ValueError, TypeError, KeyError, OSError, AttributeError,
            OverflowError, IndexError):
        return _hold(["INVALID_SETTLEMENT_INPUT"])
