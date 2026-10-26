"""Capture a fixed low-score research candidate at its own actual UTC clock.

Only a new, independently keyed object is added to newly produced shadow JSON.
Original A/B/C data remain unchanged. The existing whole-shadow archival and
signature flow can preserve these bytes, but its existing per-pair time audit
does not validate this candidate. No external witness or formal qualification
is asserted by this producer.
"""
import argparse
import copy
import hashlib
import json
import math
import os
import stat
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from retrospective_dixon_coles import probabilities
from source_fixture_identity import metadata_from_event_id
from team_identity import team_id

MODEL = "dixon-coles-fixed-rate-rho-minus005-forward-research-v1"
TOP_KEY = "fixed_low_score_challenger"
SCHEMA = "football-king-dixon-coles-forward-capture-v1"
BASE_MODEL = "poisson-shrinkage-unvalidated-v4.1"
LEAGUES = ("epl", "championship", "bundesliga", "laliga", "seriea", "ligue1")
MAX_ROWS = 3000
MAX_BYTES = 8_000_000
RHO = -.05
EXPECTED_IMPLEMENTATION_SHA256 = "25eba7408e4ec455b009b27330d94bc224456c4cd1e85b114e3bb9be776f4d02"
HK = ZoneInfo("Asia/Hong_Kong")
_DATETIME_TYPE = datetime

PROTOCOL = {
    "protocol_id": "football-king-fixed-low-score-forward-protocol-v1",
    "model_id": MODEL,
    "rho": RHO,
    "effective_from_utc": "2026-10-26T08:30:34+00:00",
    "effective_from_is_policy_not_externally_certified_registration": True,
    "base_model": BASE_MODEL,
    "source_rate_decimal_places": 5,
    "goal_grid": "0_TO_11_EACH_SIDE_NORMALIZED_THEN_ROUND_7DP",
    "selection_basis": "2024_25_DEVELOPMENT_UNROUNDED_LOG_LOSS_ONLY",
    "development_cases": 2093,
    "source_report_sha256": "ab9114b156992162409a32cb24d292a0b82d49b2833cee4369ea1ca599790dba",
    "source_archive_commit": "e6744429ee395bc86f247348c6184bb08d4eb361",
    "probability_implementation_sha256": EXPECTED_IMPLEMENTATION_SHA256,
    "parameter_refitting_permitted": False,
    "primary_baseline": "DERIVED_RHO_ZERO_ON_SAME_FIVE_DECIMAL_RATES",
    "secondary_baseline": "PUBLISHED_ORIGINAL_PROBABILITIES",
    "max_original_rho0_probability_difference": .000011,
    "rounding_bound_is_not_source_authentication": True,
    "minimum_training_games": 30,
    "maximum_source_age_seconds": 10*60*60,
    "minimum_recorded_kickoff_lead_seconds_exclusive": 600,
    "source_prediction_clock_matches_document_exact_instant": True,
    "source_event_id_policy": "EXACT_STRING_MAX512_NO_TRIMMING_ASCII_CONTROL_OR_DEL",
    "candidate_clock": "OWN_ACTUAL_COMPUTATION_COMPLETION_UTC_NOT_BASE_PREDICTION_CLOCK",
    "automatic_promotion_permitted": False,
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


_PROTOCOL_BYTES = _canonical(PROTOCOL)
PROTOCOL_SHA256 = "bfdbb5e2fe8752cbabd6a795a4003d49f112027064ee97e553da8f7411f2bddf"


def _utc(value):
    if not isinstance(value, str) or not 0 < len(value) <= 64:
        raise ValueError("INVALID_CAPTURE_TIME")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("NAIVE_CAPTURE_TIME")
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_CAPTURE_TIME") from None


def _clock(now):
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, _DATETIME_TYPE):
        raise ValueError("INVALID_CAPTURE_CLOCK")
    try:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("NAIVE_CAPTURE_CLOCK")
        return now.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("INVALID_CAPTURE_CLOCK") from None


def _text(value, maximum=512):
    return isinstance(value, str) and 0 < len(value) <= maximum and bool(value.strip())


def _source_event_id(value):
    """Validate the shared exact source-ID contract without normalization."""
    try:
        return metadata_from_event_id(value)["forecast_event_id"]
    except ValueError:
        return None


def _finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except (ValueError, OverflowError):
        return False


def _implementation_matches():
    try:
        raw = Path(__file__).with_name("retrospective_dixon_coles.py").read_bytes()
        return hashlib.sha256(raw).hexdigest() == EXPECTED_IMPLEMENTATION_SHA256
    except OSError:
        return False


def _keys(row):
    """Scan known identities before row validity, so bad duplicates poison all."""
    if not isinstance(row, dict):
        return None, None
    event = _source_event_id(row.get("event_id"))
    fixture = None
    league, home, away = row.get("league"), row.get("home"), row.get("away")
    if league in LEAGUES and _text(home, 109) and _text(away, 109):
        home_id, away_id = team_id(league, home), team_id(league, away)
        if home_id and away_id and home_id != away_id:
            try:
                fixture = (league, home_id, away_id, _utc(row.get("kickoff_utc")).isoformat())
            except ValueError:
                pass
    return event, fixture


def _case(row, source_at, now):
    if (not isinstance(row, dict) or row.get("production_recommendations") != "DISABLED"
            or row.get("model") != BASE_MODEL or row.get("league") not in LEAGUES
            or _source_event_id(row.get("event_id")) is None
            or not _text(row.get("home"), 109) or not _text(row.get("away"), 109)):
        raise ValueError("INVALID_SOURCE_ROW")
    if (any(row.get(key) is not None for key in ("score_ft", "result", "historical_outcome", "y"))
            or ("status" in row and row["status"] != "SCHEDULED")):
        raise ValueError("RESULT_BEARING_SOURCE_ROW")
    _, fixture = _keys(row)
    if fixture is None:
        raise ValueError("INVALID_SOURCE_FIXTURE")
    source_prediction = _utc(row.get("prediction_utc"))
    kickoff = _utc(row.get("kickoff_utc"))
    if source_prediction != source_at or not source_prediction <= now:
        raise ValueError("SOURCE_PREDICTION_CLOCK_MISMATCH")
    if (kickoff-now).total_seconds() <= 600:
        raise ValueError("INSUFFICIENT_OWN_CLOCK_KICKOFF_LEAD")
    count, digest = row.get("training_games"), row.get("training_observations_sha256")
    if (type(count) is not int or count < 30 or not isinstance(digest, str)
            or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("INVALID_TRAINING_PROVENANCE")
    try:
        cutoff = date.fromisoformat(row["training_cutoff_local_day"])
    except (ValueError, TypeError, KeyError):
        raise ValueError("INVALID_TRAINING_CUTOFF") from None
    if cutoff >= source_prediction.astimezone(HK).date():
        raise ValueError("TRAINING_NOT_PRIOR_LOCAL_DAY")
    rates = [row.get("expected_home_goals"), row.get("expected_away_goals")]
    if not all(_finite(v) and .1 <= v <= 5.5 and round(v, 5) == v for v in rates):
        raise ValueError("INVALID_FIVE_DECIMAL_SOURCE_RATES")
    original = [row.get(key) for key in ("p_home", "p_draw", "p_away")]
    if (not all(_finite(v) and 0 <= v <= 1 for v in original)
            or abs(sum(original)-1) > .002):
        raise ValueError("INVALID_ORIGINAL_PROBABILITIES")
    derived = probabilities(*rates, 0.0)
    difference = max(abs(a-b) for a, b in zip(original, derived))
    if difference > .000011:
        raise ValueError("ORIGINAL_RATE_PROBABILITY_INCOHERENCE")
    projection = {
        "league": row["league"], "event_id": row["event_id"],
        "home": row["home"], "away": row["away"],
        "kickoff_utc_recorded": kickoff.isoformat(),
        "source_prediction_utc": source_prediction.isoformat(),
        "source_model": row["model"], "original": original,
        "expected_home_goals": rates[0], "expected_away_goals": rates[1],
        "training_games": count, "training_cutoff_local_day": cutoff.isoformat(),
        "training_observations_sha256": digest,
    }
    return {
        **projection, "source_projection_sha256": hashlib.sha256(_canonical(projection)).hexdigest(),
        "prediction_utc": now.isoformat(), "candidate_generated_utc": now.isoformat(),
        "model_id": MODEL, "protocol_sha256": PROTOCOL_SHA256,
        "derived_rho0": derived, "candidate": probabilities(*rates, RHO),
        "original_rho0_max_probability_difference": difference,
        "original_rho0_argmax_disagreement": (
            max(range(3), key=lambda i: original[i]) != max(range(3), key=lambda i: derived[i])),
        "production_recommendations": "DISABLED",
    }


def _build_at_start(shadow, now):
    """Calculate once at a validated entry clock, before completion filtering."""
    now = _clock(now)
    output = {
        "schema": SCHEMA, "model_id": MODEL, "generated_utc": now.isoformat(),
        "source_as_of_utc": None,
        "source_report_sha256": json.loads(_PROTOCOL_BYTES)["source_report_sha256"],
        "protocol": json.loads(_PROTOCOL_BYTES), "protocol_sha256": PROTOCOL_SHA256,
        "frozen_rho": RHO, "parameter_fitting_performed": False,
        "status": "HOLD", "source_problem": None,
        "predictions_count": 0, "predictions": [], "exclusions": {},
        "maximum_original_rho0_probability_difference": None,
        "original_rho0_argmax_disagreements": 0,
        "independently_verified_prematch_capture": False,
        "candidate_witness_time_verified": False,
        "existing_paired_time_audit_covers_candidate": False,
        "actual_kickoff_independently_verified": False,
        "source_identity_independently_verified": False,
        "results_independently_verified": False,
        "prospective_qualification_verified": False,
        "model_calibration_certified": False,
        "market_baseline_available": False, "betting_roi_estimable": False,
        "automatic_model_promotion": False, "production_recommendations": "DISABLED",
        "goal_rates_are_rounded_source_approximations": True,
        "sealed_score_distribution_reconstructed": False,
        "limitations": [
            "Own runtime clock only; no externally verified candidate witness or registration time is asserted.",
            "Recorded kickoff and source identity are not independently authenticated actual kickoff or native-ID evidence.",
            "Existing paired forecast time audit does not audit this separate candidate row set.",
            "Whole-shadow archival/signatures may preserve these bytes; Git history is administrator-mutable.",
            "Five-decimal rates approximate the original unrounded rates, not a sealed score distribution.",
            "No efficacy, market superiority, calibrated probabilities, executable prices, ROI or formal qualification is established.",
        ],
    }
    try:
        registered = (hashlib.sha256(_canonical(PROTOCOL)).hexdigest() == PROTOCOL_SHA256
                      and RHO == PROTOCOL["rho"]
                      and EXPECTED_IMPLEMENTATION_SHA256 == PROTOCOL["probability_implementation_sha256"])
    except (KeyError, ValueError, TypeError, OverflowError):
        registered = False
    if not registered:
        output["source_problem"] = "FROZEN_PROTOCOL_DIGEST_MISMATCH"
        return output
    if not _implementation_matches():
        output["source_problem"] = "FROZEN_PROBABILITY_IMPLEMENTATION_MISMATCH"
        return output
    effective = _utc(PROTOCOL["effective_from_utc"])
    if now < effective:
        output["source_problem"] = "BEFORE_PROTOCOL_EFFECTIVE_FROM"
        return output
    if not isinstance(shadow, dict):
        output["source_problem"] = "INVALID_SOURCE_DOCUMENT"
        return output
    rows = shadow.get("predictions")
    if (shadow.get("schema") != "football-king-uncalibrated-shadow-1"
            or shadow.get("production_recommendations") != "DISABLED"
            or not isinstance(rows, list) or len(rows) > MAX_ROWS
            or type(shadow.get("predictions_count")) is not int
            or shadow["predictions_count"] != len(rows)
            or shadow.get("status") != ("SHADOW_ONLY" if rows else "HOLD")):
        output["source_problem"] = "INVALID_SOURCE_DOCUMENT"
        return output
    try:
        source_at = _utc(shadow.get("as_of_utc"))
    except ValueError:
        output["source_problem"] = "INVALID_SOURCE_DOCUMENT_CLOCK"
        return output
    output["source_as_of_utc"] = source_at.isoformat()
    if source_at < effective or not 0 <= (now-source_at).total_seconds() <= 36000:
        output["source_problem"] = "SOURCE_BEFORE_PROTOCOL_OR_STALE_OR_FUTURE"
        return output
    identities = [_keys(row) for row in rows]
    events = Counter(event for event, _ in identities if event is not None)
    fixtures = Counter(fixture for _, fixture in identities if fixture is not None)
    excluded = Counter()
    for row, (event, fixture) in zip(rows, identities):
        if (event is not None and events[event] > 1) or (fixture is not None and fixtures[fixture] > 1):
            excluded["AMBIGUOUS_SOURCE_IDENTITY"] += 1
            continue
        try:
            output["predictions"].append(_case(row, source_at, now))
        except (ValueError, TypeError, OverflowError) as exc:
            excluded[str(exc) if isinstance(exc, ValueError) else "INVALID_SOURCE_ROW"] += 1
    output["exclusions"] = dict(excluded)
    accepted = output["predictions"]
    output["predictions_count"] = len(accepted)
    if accepted:
        output["status"] = "FORWARD_RESEARCH_CAPTURE_ONLY"
        output["maximum_original_rho0_probability_difference"] = max(
            row["original_rho0_max_probability_difference"] for row in accepted)
        output["original_rho0_argmax_disagreements"] = sum(
            row["original_rho0_argmax_disagreement"] for row in accepted)
    return output


def _summarize_capture(output):
    rows = output["predictions"]
    output["predictions_count"] = len(rows)
    output["status"] = "FORWARD_RESEARCH_CAPTURE_ONLY" if rows else "HOLD"
    output["maximum_original_rho0_probability_difference"] = (
        max(row["original_rho0_max_probability_difference"] for row in rows) if rows else None)
    output["original_rho0_argmax_disagreements"] = sum(
        row["original_rho0_argmax_disagreement"] for row in rows)


def build(shadow, *, now=None):
    """Use the actual computation-completion clock; explicit now is offline-only.

    Calculate each candidate just once from the already supplied source. Then
    check the real completion clock, source age and every retained kickoff,
    without recomputing probabilities or accessing outcomes.
    """
    start = _clock(now)
    output = _build_at_start(shadow, start)
    if now is not None:
        return output
    completed = _clock(None)
    output["generated_utc"] = completed.isoformat()
    if completed < start:
        output["source_problem"] = "CAPTURE_CLOCK_REWOUND"
        output["predictions"] = []
    elif output["source_as_of_utc"] is not None:
        source_at = _utc(output["source_as_of_utc"])
        effective = _utc(json.loads(_PROTOCOL_BYTES)["effective_from_utc"])
        if completed < effective or source_at < effective or not 0 <= (completed-source_at).total_seconds() <= 36000:
            output["source_problem"] = "SOURCE_CLOCK_INVALID_AT_COMPLETION"
            output["predictions"] = []
    retained = []
    for row in output["predictions"]:
        if (_utc(row["kickoff_utc_recorded"])-completed).total_seconds() <= 600:
            key = "INSUFFICIENT_OWN_CLOCK_KICKOFF_LEAD"
            output["exclusions"][key] = output["exclusions"].get(key, 0)+1
            continue
        row["prediction_utc"] = completed.isoformat()
        row["candidate_generated_utc"] = completed.isoformat()
        retained.append(row)
    output["predictions"] = retained
    _summarize_capture(output)
    return output


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_SOURCE_JSON_KEY")
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError("NONFINITE_SOURCE_JSON")


def publish(site, *, now=None):
    """Add only the new top-level object; refuse replacing any prior capture."""
    path = Path(site)/"shadow.json"
    source_stat = path.lstat()
    if not stat.S_ISREG(source_stat.st_mode) or path.is_symlink():
        raise ValueError("NONREGULAR_SOURCE_SHADOW")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES+1)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("SOURCE_SHADOW_SIZE_LIMIT")
    shadow = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    if not isinstance(shadow, dict) or TOP_KEY in shadow:
        raise ValueError("PRIOR_CAPTURE_OR_INVALID_SOURCE_DOCUMENT")
    # Capture after reading the input, immediately before the transformation.
    result = build(shadow, now=now)
    shadow[TOP_KEY] = result
    payload = json.dumps(shadow, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    if len(payload.encode("utf-8")) > MAX_BYTES:
        raise ValueError("CAPTURED_SHADOW_SIZE_LIMIT")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".shadow-dc-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        try:
            os.fchmod(descriptor, stat.S_IMODE(source_stat.st_mode))
            stream = os.fdopen(descriptor, "w", encoding="utf-8")
        except BaseException:
            os.close(descriptor)
            raise
        with stream:
            stream.write(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return copy.deepcopy(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="app/site")
    args = parser.parse_args()
    result = publish(args.site)
    print(json.dumps({"model_id": MODEL, "status": result["status"],
                      "predictions_count": result["predictions_count"],
                      "generated_utc": result["generated_utc"],
                      "production_recommendations": "DISABLED"}))
