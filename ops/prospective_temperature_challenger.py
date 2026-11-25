"""Time-locked, abstaining, research-only probability calibration challenger.

Never rewrite original A/B/C/D forecasts. The source-admission booleans below
are REQUIRED assertions from an independent evidence pipeline, not cryptographic
proof verified by this module. A caller cannot self-certify a true prospective
sample merely by setting them to True. No market prices, EV or betting here.
"""
from datetime import datetime, timedelta, timezone
import math

MODEL = "time-locked-multiclass-temperature-research-v1"
MIN_TRAIN = 90
MIN_VALIDATION = 30
MIN_DISTINCT_WEEKS = 8
TEMPERATURES = tuple(round(1 + i * 0.05, 2) for i in range(21))
PROOF_FIELDS = (
    "forecast_provenance_independently_attested",
    "fixture_result_source_independently_verified",
    "fixture_identity_independently_verified",
)


def _hold(reason):
    return {
        "schema": "football-king-time-locked-calibration-research-v1",
        "model": MODEL,
        "status": "HOLD",
        "reason": reason,
        "train_count": 0,
        "validation_count": 0,
        "candidate": None,
        "production_recommendations": "DISABLED",
        "verified_positive_ev": False,
        "model_promoted": False,
        "eligible_for_formal_forward_scoring": False,
        "external_attestation_verified_by_this_module": False,
        "original_sealed_forecasts_modified": False,
    }


def _utc(value):
    if type(value) is not str or len(value) > 40:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return dt.astimezone(timezone.utc)


def _probabilities(value):
    if type(value) not in (list, tuple) or len(value) != 3:
        raise ValueError("INVALID_PROBABILITIES")
    if any(type(x) not in (int, float) or not math.isfinite(x)
           or not 0 < x < 1 for x in value):
        raise ValueError("INVALID_PROBABILITIES")
    total = math.fsum(value)
    if abs(total - 1) > 1e-6:
        raise ValueError("NOT_NORMALIZED")
    return tuple(float(x) / total for x in value)


def _temperature(probs, temp):
    if temp not in TEMPERATURES:
        raise ValueError("UNDECLARED_TEMPERATURE")
    weights = tuple(math.exp(math.log(p) / temp) for p in probs)
    total = math.fsum(weights)
    return tuple(x / total for x in weights)


def _loss(rows, temp):
    # Per-event multiclass log loss and Brier (three-category, unhalved).
    ll, br = [], []
    for row in rows:
        p = _temperature(row["p"], temp)
        y = row["y"]
        ll.append(-math.log(p[y]))
        br.append(math.fsum((v - int(i == y)) ** 2 for i, v in enumerate(p)))
    n = len(rows)
    return {"log_loss": math.fsum(ll) / n, "brier": math.fsum(br) / n}


def _case_id(value):
    return (type(value) is str and 4 <= len(value) <= 128
            and value == value.strip()
            and not any(ch.isspace() for ch in value))


def _candidate(value, as_of):
    if type(value) is not dict:
        raise ValueError("INVALID_CANDIDATE")
    if any(key in value for key in ("y", "result", "score_ft", "settled_utc")):
        raise ValueError("CANDIDATE_CONTAINS_RESULT")
    league, event = value.get("league"), value.get("source_event_id")
    if type(league) is not str or not league or not _case_id(event):
        raise ValueError("CANDIDATE_IDENTITY_MISSING")
    if value.get("production_recommendations") != "DISABLED":
        raise ValueError("UNSAFE_CANDIDATE")
    predicted, kickoff = _utc(value.get("forecast_utc")), _utc(value.get("kickoff_utc"))
    if not predicted < as_of < kickoff:
        raise ValueError("CANDIDATE_NOT_STRICTLY_PREMATCH")
    return league, event, predicted, _probabilities(value.get("p"))


def compare(history, candidate, *, as_of_utc):
    """Fit only earlier independently claimed evidence, then walk-forward validate.

    Validation is chronological, and all *training settlements* must predate
    the first validation forecast. The validation split is a research check,
    NOT an independent future prospective trial or approval for deployment.
    """
    output = _hold("INVALID_INPUT")
    try:
        as_of = _utc(as_of_utc)
        league, event, cutoff, p = _candidate(candidate, as_of)
    except (ValueError, TypeError) as exc:
        output["reason"] = str(exc)
        return output
    if type(history) is not list or len(history) > 10000:
        output["reason"] = "INVALID_OR_OVERSIZED_HISTORY"
        return output

    included = []
    seen = set()
    rejected_unverified = 0
    for value in history:
        if type(value) is not dict or value.get("league") != league:
            continue
        # A proof *claim* does not authenticate an original-source artifact;
        # evidence pipeline must check its own cryptographic/native origins.
        if any(value.get(field) is not True for field in PROOF_FIELDS):
            rejected_unverified += 1
            continue
        try:
            case_id = value.get("source_event_id")
            if not _case_id(case_id):
                raise ValueError("HISTORY_EVENT_ID_INVALID")
            fp = _utc(value.get("forecast_utc"))
            kick = _utc(value.get("kickoff_utc"))
            settled = _utc(value.get("settled_utc"))
            y = value.get("y")
            if type(y) is not int or y not in (0, 1, 2):
                raise ValueError("INVALID_OUTCOME")
            if value.get("production_recommendations") != "DISABLED":
                raise ValueError("UNSAFE_HISTORY")
            probs = _probabilities(value.get("p"))
            if not (fp < kick and kick + timedelta(minutes=90) <= settled <= cutoff):
                # No late-settled cases or future results admitted.
                continue
            if case_id == event or case_id in seen:
                raise ValueError("DUPLICATE_OR_CANDIDATE_RESULT_ID")
            seen.add(case_id)
            included.append({
                "id": case_id, "forecast": fp, "kickoff": kick,
                "settled": settled, "p": probs, "y": y,
            })
        except (ValueError, TypeError) as exc:
            output["reason"] = str(exc)
            return output

    included.sort(key=lambda row: (row["kickoff"], row["id"]))
    output["admitted_before_candidate"] = len(included)
    output["rejected_unverified"] = rejected_unverified
    if len(included) < MIN_TRAIN + MIN_VALIDATION:
        output["reason"] = "INSUFFICIENT_INDEPENDENT_PREMATCH_HISTORY"
        return output
    weeks = {(x["kickoff"].isocalendar().year, x["kickoff"].isocalendar().week)
             for x in included}
    if len(weeks) < MIN_DISTINCT_WEEKS:
        output["reason"] = "INSUFFICIENT_TEMPORAL_COVERAGE"
        return output

    # Last quarter is holdout. History must be settled *before* the first
    # holdout model timestamp, not merely before its kickoff.
    holdout_size = max(MIN_VALIDATION, len(included) // 4)
    boundary = included[-holdout_size]["kickoff"]
    # Keep every simultaneous kickoff together in the holdout. Do not
    # let arbitrary event IDs select which matches are evaluated.
    training = [row for row in included if row["kickoff"] < boundary]
    validation = [row for row in included if row["kickoff"] >= boundary]
    validation_start = min(x["forecast"] for x in validation)
    training = [x for x in training if x["settled"] < validation_start]
    output["train_count"] = len(training)
    output["validation_count"] = len(validation)
    if len(training) < MIN_TRAIN:
        output["reason"] = "TRAIN_SETTLEMENT_NOT_PRIOR_TO_VALIDATION"
        return output

    # Fixed, public finite temperature grid: never tune on candidate results.
    fitted_temp = min(TEMPERATURES, key=lambda temp: (_loss(training, temp)["log_loss"], temp))
    original = _loss(validation, 1.0)
    challenger = _loss(validation, fitted_temp)
    output["fitted_temperature"] = fitted_temp
    output["validation_original"] = {k: round(v, 8) for k, v in original.items()}
    output["validation_challenger"] = {k: round(v, 8) for k, v in challenger.items()}
    output["validation_split"] = "chronological_last_quarter"
    output["validation_training_cutoff_utc"] = validation_start.isoformat()
    output["attestation_input_flags_are_not_self_verifying"] = True

    # Both proper scores must improve on this research split; no promotion.
    if (fitted_temp <= 1.0
            or challenger["log_loss"] >= original["log_loss"] - 1e-5
            or challenger["brier"] >= original["brier"] - 1e-5):
        output["reason"] = "NO_CONSISTENT_VALIDATION_IMPROVEMENT"
        return output
    adjusted = _temperature(p, fitted_temp)
    output["status"] = "RESEARCH_ONLY"
    output["reason"] = "RETROSPECTIVE_VALIDATION_ONLY_NOT_PROSPECTIVE_PROOF"
    output["candidate"] = {
        "league": league,
        "source_event_id_unverified": event,
        "forecast_utc_original": cutoff.isoformat(),
        "unchanged_original_probabilities": [round(x, 7) for x in p],
        "calibrated_research_probabilities": [round(x, 7) for x in adjusted],
        "temperature": fitted_temp,
        "verified_out_of_sample_improvement": False,
        "betting_eligible": False,
    }
    return output
