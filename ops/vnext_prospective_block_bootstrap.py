"""VNext PR-06: paired UTC-week block bootstrap over locally sealed forecasts.

Requires complete, predeclared fixture universe, two named frozen models and
source-agreeing *unverified* later results. Descriptive confidence intervals
remain EXPLORATORY: local timestamps/manifest, source truth and independent
upstream are not externally attested. No model promotion, betting or EV.
"""
import math
import random
from collections import defaultdict
from datetime import timezone

from vnext_prospective_local_seal import (
    audit_source_independence, read_forecast_seal,
)
from vnext_shadow_forward_audit import _clock, _id, _row, _score

SCHEMA = "football-king-vnext-prospective-block-bootstrap-v1"
MIN_FIXTURES = 300
MIN_WEEKS = 12
MAX_FIXTURES = 3000
BOOTSTRAPS = 500
RANDOM_SEED = 20261104
CASE_FIELDS = frozenset({"file_name", "content_sha256", "result", "result_observations"})
MANIFEST_FIELDS = frozenset({
    "cohort_id", "fixture_ids", "registered_utc", "training_cutoff_utc",
    "baseline_model_id", "challenger_model_id", "evaluation_end_utc",
    "primary_metric", "resampling_unit", "production_recommendations",
})


def _hold(reason):
    return {
        "schema": SCHEMA, "status": "HOLD", "reason": reason,
        "independently_verified_real_oos": False,
        "model_accuracy_improvement_verified": False,
        "market_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def _percentile(sorted_values, fraction):
    v = (len(sorted_values) - 1) * fraction
    lo = int(v)
    hi = min(len(sorted_values) - 1, lo + 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (v - lo)


def _interval(weeks, field):
    rng = random.Random(RANDOM_SEED)
    groups = [weeks[key] for key in sorted(weeks)]
    values = []
    for _ in range(BOOTSTRAPS):
        selected = [groups[rng.randrange(len(groups))] for _ in groups]
        numerator = math.fsum(sum(row[field] for row in group) for group in selected)
        denominator = sum(len(group) for group in selected)
        values.append(numerator / denominator)
    values.sort()
    return [_percentile(values, .025), _percentile(values, .975)]


def evaluate_sealed_holdout(root, manifest, cases, *, evaluated_utc):
    """One complete cohort or fail-closed. No cherry-picking or backfill."""
    evaluated = _clock(evaluated_utc)
    if type(manifest) is not dict or set(manifest) != MANIFEST_FIELDS:
        raise ValueError("INVALID_HOLDOUT_MANIFEST")
    if (not _id(manifest["cohort_id"]) or
            not _id(manifest["baseline_model_id"]) or
            not _id(manifest["challenger_model_id"]) or
            manifest["baseline_model_id"] == manifest["challenger_model_id"] or
            manifest["primary_metric"] != "LOG_LOSS" or
            manifest["resampling_unit"] != "UTC_ISO_WEEK" or
            manifest["production_recommendations"] != "DISABLED"):
        raise ValueError("INVALID_FROZEN_COHORT_PROTOCOL")
    registered = _clock(manifest["registered_utc"])
    training_cutoff = _clock(manifest["training_cutoff_utc"])
    window_end = _clock(manifest["evaluation_end_utc"])
    if not training_cutoff < registered < window_end <= evaluated:
        raise ValueError("INVALID_HOLDOUT_CHRONOLOGY")
    if type(cases) is not list or not MIN_FIXTURES <= len(cases) <= MAX_FIXTURES:
        raise ValueError("INSUFFICIENT_OR_EXCESSIVE_PAIRED_FIXTURES")
    names = manifest["fixture_ids"]
    if (type(names) is not list or len(names) != len(cases) or
            any(not _id(fid) for fid in names) or len(set(names)) != len(names)):
        raise ValueError("INVALID_OR_INCOMPLETE_COHORT_UNIVERSE")

    records = []
    seen = set()
    for case in cases:
        if type(case) is not dict or set(case) != CASE_FIELDS:
            raise ValueError("INVALID_ARCHIVE_RESULT_JOIN_SCHEMA")
        sealed = read_forecast_seal(root, case["file_name"],
                                    expected_sha256=case["content_sha256"])
        pair = sealed["pair"]
        fid = pair["fixture_id"]
        if fid in seen:
            raise ValueError("DUPLICATE_FIXTURE_OR_MULTIPLE_CUTS")
        seen.add(fid)
        kickoff, forecast, capture = (
            _clock(pair["kickoff_utc"]), _clock(pair["as_of_utc"]),
            _clock(sealed["recorded_at_utc"]),
        )
        if not training_cutoff < registered <= forecast <= capture < kickoff:
            raise ValueError("CANDIDATE_NOT_SEALED_AFTER_REGISTERED_MANIFEST")
        if kickoff > window_end:
            raise ValueError("FIXTURE_OUTSIDE_PREREGISTERED_WINDOW")
        if (pair["models"]["baseline"]["model_id"] != manifest["baseline_model_id"] or
                pair["models"]["challenger"]["model_id"] != manifest["challenger_model_id"]):
            raise ValueError("UNEXPECTED_MODEL_VERSION")
        observation = audit_source_independence(
            case["result_observations"], fixture_id=fid,
            decision_utc=case["result"]["result_received_utc"])
        if not observation["observation_agreement"]:
            raise ValueError("UNCONFIRMED_OR_CONFLICTING_RESULT_SOURCES")
        a = case["result_observations"][0]
        if (a["home_goals"] != case["result"]["home_goals"] or
                a["away_goals"] != case["result"]["away_goals"]):
            raise ValueError("RESULT_DISAGREES_WITH_SOURCE_OBSERVATIONS")
        # Reuse PR-05 strict as-of evaluation against a later distinct result.
        result = _row({"pair": pair, "result": case["result"]}, evaluated=evaluated)
        week = kickoff.isocalendar()[:2]
        baseline = _score(result["baseline"], result["y"])
        challenger = _score(result["challenger"], result["y"])
        records.append({
            "fixture_id": fid, "week": week,
            "ll_diff": baseline[0] - challenger[0],
            "brier_diff": baseline[1] - challenger[1],
            "draw_brier_diff": (
                (result["baseline"][1] - int(result["y"] == 1)) ** 2 -
                (result["challenger"][1] - int(result["y"] == 1)) ** 2
            ),
        })
    if seen != set(names):
        raise ValueError("MISSING_OR_EXTRA_HOLDOUT_FIXTURES")
    weeks = defaultdict(list)
    for row in records:
        weeks[row["week"]].append(row)
    if len(weeks) < MIN_WEEKS:
        raise ValueError("INSUFFICIENT_DISTINCT_UTC_WEEKS")
    records.sort(key=lambda row: row["fixture_id"])
    n = len(records)
    means = {k: math.fsum(row[k] for row in records) / n
             for k in ("ll_diff", "brier_diff", "draw_brier_diff")}
    ci = {k: _interval(weeks, k) for k in means}
    return {
        "schema": SCHEMA, "status": "EXPLORATORY_ONLY",
        "fixture_count": n, "distinct_utc_iso_weeks": len(weeks),
        "baseline_model_id": manifest["baseline_model_id"],
        "challenger_model_id": manifest["challenger_model_id"],
        "primary_metric": "LOG_LOSS",
        "paired_baseline_minus_challenger": means,
        "week_cluster_percentile_95_intervals_unverified": ci,
        "bootstrap_replicates": BOOTSTRAPS,
        "fixed_research_seed": RANDOM_SEED,
        "source_observation_agreement_n": n,
        "independently_verified_result_n": 0,
        "manifest_externally_registered": False,
        "archive_clock_externally_attested": False,
        "independent_sources_certified": False,
        "true_holdout_unsealed_until_scoring": False,
        "independently_verified_real_oos": False,
        "model_accuracy_improvement_verified": False,
        "model_eligible_for_promotion": False,
        "market_ev_verified": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def audit_sealed_holdout(root, manifest, cases, *, evaluated_utc):
    try:
        return evaluate_sealed_holdout(
            root, manifest, cases, evaluated_utc=evaluated_utc)
    except (ValueError, KeyError, TypeError, OSError, OverflowError) as exc:
        return _hold(str(exc) or "INVALID_HOLDOUT_INPUT")
