"""Observe the *actual* existing daily A shadow run; no second source fetch.

Use this as a drop-in CLI wrapper for the existing daily forecast generation
step. This does not alter original poisson calculations or stored predictions:
the observer delegates unchanged calls to shadow_forecast.predict_league.
Captures are process-local evidence of a Python function invocation, NOT
independent source authentication, attested timestamps, or OOS scoring.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path

import shadow_forecast

SCHEMA = "football-king-original-A-live-execution-observation-v1"
MAX_RUN_SECONDS = 1200


def _hash(value):
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _time(value):
    if type(value) is not str:
        raise ValueError("INVALID_MODEL_TIME")
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("INVALID_MODEL_TIME")
    return d.astimezone(timezone.utc)


# Original-A fields that must remain unchanged after any optional research
# overlay. The original generator intentionally restamps prediction_utc at
# completion, so that one field is checked separately against batch as_of.
# Native IDs are attached AFTER predict_league by the source gateway and are
# sealed independently in event_ids_unverified.
ORIGINAL_A_IMMUTABLE_FIELDS = (
    "league", "event_id", "home", "away", "kickoff_utc",
    "model", "training_games", "training_cutoff_local_day",
    "training_observations_sha256", "p_home", "p_draw", "p_away",
    "expected_home_goals", "expected_away_goals", "schedule_utc_source",
    "schedule_time_agreement_only_not_result_verification",
    "calibrated", "verified_market_odds", "production_recommendations",
)


def _forecast_signature(row):
    return _hash([row[k] for k in ORIGINAL_A_IMMUTABLE_FIELDS])


def _native_fixture_fails_closed(row):
    native = row.get("native_fixture_input")
    if native is None:
        return False
    return (type(native) is not dict
            or native.get("schema") != "football-king-native-fixture-input-observation-v1"
            or native.get("status") != "UNAUTHENTICATED"
            or native.get("native_ids_from_same_response_as_gateway_fixture") is not True
            or any(native.get(k) is not False for k in (
                "source_identity_authenticated", "source_capture_authenticated",
                "raw_input_durably_archived", "native_ids_used_as_model_features",
                "eligible_for_model_scoring")))


def _native_receipt_sha(row):
    return (_hash(row["native_fixture_input"])
            if "native_fixture_input" in row else None)


def run_once(*, generator, clock, version_sha=None):
    """Observe the production shadow generator exactly ONCE, no new requests.

    The monkey-patch is scoped to this synchronous call, and always restored.
    Each wrapper call delegates to the original unmodified predict_league.
    """
    entered = clock()
    if type(entered) is not datetime or entered.tzinfo is None or entered.utcoffset() is None:
        raise ValueError("NAIVE_EXECUTION_CLOCK")
    entered = entered.astimezone(timezone.utc)
    original = shadow_forecast.predict_league
    observed = []
    def spy(rows, league, now):
        call = {
            "league": league,
            "invoked": True,
            "input_rows_sha256_not_provider_proof": _hash(rows),
            "model_argument_time_utc": now.astimezone(timezone.utc).isoformat(),
        }
        try:
            result = original(rows, league, now)
        except Exception:
            call["success"] = False
            observed.append(call)
            raise
        call["success"] = True
        call["produced_event_ids_unverified"] = [
            row["event_id"] for row in result]
        call["output_signatures_sha256"] = [
            _forecast_signature(row) for row in result]
        observed.append(call)
        return result

    try:
        shadow_forecast.predict_league = spy
        result = generator()
    finally:
        shadow_forecast.predict_league = original
    completed = clock()
    if type(completed) is not datetime or completed.tzinfo is None or completed.utcoffset() is None:
        raise ValueError("NAIVE_EXECUTION_CLOCK")
    completed = completed.astimezone(timezone.utc)
    if (completed < entered or completed - entered >
            timedelta(seconds=MAX_RUN_SECONDS)):
        raise ValueError("UNSAFE_MODEL_EXECUTION_CLOCK")
    if (type(result) is not dict or result.get("schema") !=
            "football-king-uncalibrated-shadow-1"
            or result.get("production_recommendations") != "DISABLED"
            or type(result.get("predictions")) is not list
            or result.get("predictions_count") != len(result["predictions"])):
        raise ValueError("UNSAFE_OR_INVALID_ORIGINAL_SHADOW")
    asof = _time(result.get("as_of_utc"))
    if not (entered <= asof <= completed):
        raise ValueError("ORIGINAL_ASOF_OUTSIDE_ACTUAL_RUN")
    seen = set()
    invocation_events = {}
    for call in observed:
        if call["league"] not in shadow_forecast.LEAGUES:
            raise ValueError("UNSUPPORTED_MODEL_CALL")
        if call.get("success") is True:
            for eid, digest in zip(
                    call["produced_event_ids_unverified"],
                    call["output_signatures_sha256"]):
                token = (call["league"], eid)
                if token in invocation_events:
                    raise ValueError("DUPLICATED_MODEL_INVOCATION_EVENT")
                invocation_events[token] = digest
    for row in result["predictions"]:
        if type(row) is not dict or row.get("production_recommendations") != "DISABLED":
            raise ValueError("UNSAFE_EVENT_FORECAST")
        if _native_fixture_fails_closed(row):
            raise ValueError("UNSAFE_NATIVE_FIXTURE_PROVENANCE")
        token = (row.get("league"), row.get("event_id"))
        if (token in seen or token not in invocation_events
                or row.get("prediction_utc") != result["as_of_utc"]
                or _forecast_signature(row) != invocation_events[token]):
            raise ValueError("FORECAST_NOT_FROM_THIS_INVOCATION")
        seen.add(token)
    try:
        code_sha = hashlib.sha256(
            Path(shadow_forecast.__file__).read_bytes()).hexdigest()
        original_predictions_sha = _hash(result["predictions"])
    except (OSError, TypeError, ValueError):
        raise ValueError("UNHASHABLE_OR_MISSING_MODEL_PROOF") from None

    return result, {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY" if seen else "HOLD",
        "reason": ("OBSERVED_REAL_ORIGINAL_A_FUNCTION_INVOCATION_UNATTESTED"
                   if seen else "NO_ELIGIBLE_OBSERVED_FORECAST"),
        "as_of_utc": asof.isoformat(),
        "run_entered_utc": entered.isoformat(),
        "run_completed_utc": completed.isoformat(),
        "git_commit_sha_unverified_metadata": (
            version_sha if type(version_sha) is str
            and len(version_sha) == 40
            and all(c in "0123456789abcdef" for c in version_sha) else None),
        "model_code_sha256": code_sha,
        "original_predictions_sha256_before_later_research_overlays": original_predictions_sha,
        "original_A_function_calls": len(observed),
        "successful_original_A_function_calls": sum(c["success"] is True for c in observed),
        "valid_original_A_fixture_outputs": len(seen),
        "event_ids_unverified": [
            {"league": row["league"], "source_event_id_unverified": row["event_id"],
             "native_fixture_input_sha256_not_source_attestation":
                 _native_receipt_sha(row)}
            for row in result["predictions"]
        ],
        "invocation_trace": observed,
        "model_execution_observed": bool(seen),
        "model_invocation_externally_attested": False,
        "source_identity_authenticated": False,
        "raw_source_capture_authenticated": False,
        "historical_kickoff_times_independently_attested": False,
        "result_verified_independently": False,
        "live_model_calibrated": False,
        "odds_available": False,
        "verified_positive_ev": False,
        "formal_forward_scoring_eligible": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--finished-output", required=True)
    p.add_argument("--receipt-output", required=True)
    p.add_argument("--secondary", default="sources/latest.json")
    p.add_argument("--market-schedule", default="market/latest.json")
    a = p.parse_args(argv)
    def safe_read(path):
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
            return value if type(value) is dict else None
        except (OSError, UnicodeError, ValueError):
            return None
    def generator():
        return shadow_forecast.generate(
            return_finished=True,
            secondary_snapshot=safe_read(a.secondary),
            market_schedule=safe_read(a.market_schedule))
    result, receipt = run_once(
        generator=generator, clock=lambda: datetime.now(timezone.utc),
        version_sha=os.environ.get("GITHUB_SHA"))
    internal = result.pop("_internal_finished_results", None)
    if (type(internal) is not dict or
            internal.get("production_recommendations") != "DISABLED"):
        raise ValueError("UNSAFE_FINISHED_OBSERVATIONS")
    destinations = [
        (Path(a.output), result),
        (Path(a.finished_output), internal),
        (Path(a.receipt_output), receipt),
    ]
    for path, data in destinations:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8")
    print(json.dumps({
        "as_of_utc": receipt["as_of_utc"],
        "model_calls": receipt["original_A_function_calls"],
        "observed_event_forecasts": receipt["valid_original_A_fixture_outputs"],
        "status": receipt["status"],
        "production_recommendations": "DISABLED"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
