"""Offline paired shadow validation and quote evidence gate (VNext PR-05).

This module does NOT authenticate sources, historical clocks, score truth or
bookmaker executability. All performance figures are unverified exploratory
descriptive scores, NOT an OOS certificate. No betting or positive EV claims.
"""
import hashlib
import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from score_distribution_vnext import grade_score

SCHEMA = "football-king-vnext-forward-evidence-v1"
MIN_PAIRED_FIXTURES = 30
MAX_PAIRED_FIXTURES = 3000
FORECAST_FIELDS = frozenset({
    "model_id", "forecast_utc", "inputs_available_utc", "input_sha256",
    "probabilities_1x2", "calibrated", "production_recommendations",
})
PAIR_FIELDS = frozenset({"fixture_id", "kickoff_utc", "as_of_utc", "models"})
RESULT_FIELDS = frozenset({
    "fixture_id", "home_goals", "away_goals", "result_received_utc",
    "result_source", "raw_sha256", "independently_authenticated",
})
CASE_FIELDS = frozenset({"pair", "result"})
QUOTE_FIELDS = frozenset({
    "fixture_id", "bookmaker", "quote_id", "market", "side", "line",
    "decimal_odds", "scope", "provider_updated_utc",
    "captured_utc", "received_utc", "available_utc",
    "raw_sha256", "licensed_and_executable_independently_verified",
})


def _clock(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if d.tzinfo is None or d.utcoffset() is None:
            raise ValueError("NAIVE_TIMESTAMP")
        return d.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc


def _id(value):
    return (type(value) is str and 1 <= len(value) <= 128
            and value == value.strip() and value.isprintable())


def _sha(value):
    return (type(value) is str and len(value) == 64
            and all(ch in "0123456789abcdef" for ch in value))


def _hash(value):
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _probabilities(value):
    if (type(value) not in (tuple, list) or len(value) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or not 0 < v < 1 for v in value)
            or abs(math.fsum(value) - 1) > 1e-7):
        raise ValueError("INVALID_PROBABILITIES")
    return tuple(float(v) for v in value)


def _model(model, *, kickoff, as_of):
    if type(model) is not dict or set(model) != FORECAST_FIELDS:
        raise ValueError("INVALID_FROZEN_MODEL_SCHEMA")
    if (not _id(model["model_id"]) or not _sha(model["input_sha256"])
            or model["calibrated"] is not False
            or model["production_recommendations"] != "DISABLED"):
        raise ValueError("INVALID_FROZEN_MODEL")
    forecast, inputs = _clock(model["forecast_utc"]), _clock(model["inputs_available_utc"])
    if not inputs <= forecast == as_of <= kickoff - timedelta(minutes=10):
        raise ValueError("FUTURE_INPUT_OR_UNPAIRED_CLOCK")
    return _probabilities(model["probabilities_1x2"])


def _row(case, *, evaluated):
    if type(case) is not dict or set(case) != CASE_FIELDS:
        raise ValueError("INVALID_FORWARD_CASE_SCHEMA")
    pair, result = case["pair"], case["result"]
    if type(pair) is not dict or set(pair) != PAIR_FIELDS:
        raise ValueError("INVALID_PAIR_SCHEMA")
    if type(result) is not dict or set(result) != RESULT_FIELDS:
        raise ValueError("INVALID_RESULT_SCHEMA")
    fid = pair["fixture_id"]
    if (not _id(fid) or result["fixture_id"] != fid
            or not _id(result["result_source"])
            or not _sha(result["raw_sha256"])
            or result["independently_authenticated"] is not False):
        raise ValueError("UNVERIFIED_RESULT_CLAIMS_OR_IDENTITY")
    kickoff, as_of, received = (
        _clock(pair["kickoff_utc"]),
        _clock(pair["as_of_utc"]),
        _clock(result["result_received_utc"]),
    )
    if not kickoff + timedelta(minutes=90) <= received <= evaluated:
        raise ValueError("RESULT_NOT_AVAILABLE_AT_EVALUATION")
    if type(pair["models"]) is not dict or set(pair["models"]) != {"baseline", "challenger"}:
        raise ValueError("REQUIRE_MATCHED_TWO_MODELS")
    baseline, challenger = pair["models"]["baseline"], pair["models"]["challenger"]
    p = _model(baseline, kickoff=kickoff, as_of=as_of)
    q = _model(challenger, kickoff=kickoff, as_of=as_of)
    if baseline["model_id"] == challenger["model_id"]:
        raise ValueError("DUPLICATED_MODEL_ID")
    gh, ga = result["home_goals"], result["away_goals"]
    if (type(gh) is not int or type(ga) is not int
            or not 0 <= gh <= 30 or not 0 <= ga <= 30):
        raise ValueError("INVALID_REGULATION_RESULT")
    y = 0 if gh > ga else 1 if gh == ga else 2
    return {
        "fixture_id": fid, "as_of": as_of, "kickoff": kickoff, "y": y,
        "baseline": p, "challenger": q,
        "baseline_id": baseline["model_id"], "challenger_id": challenger["model_id"],
        "self_asserted_input_hashes": (baseline["input_sha256"], challenger["input_sha256"]),
    }


def _score(p, outcome):
    # 3-class Brier without rescaling; RPS normalized by two cumulative terms.
    ll = -math.log(p[outcome])
    bs = math.fsum((v - int(i == outcome)) ** 2 for i, v in enumerate(p))
    rps = ((p[0] - int(outcome == 0)) ** 2
           + (p[0] + p[1] - int(outcome <= 1)) ** 2) / 2
    return (ll, bs, rps)


def _calibration(rows, model):
    output = []
    for index, name in enumerate(("HOME", "DRAW", "AWAY")):
        bins = []
        for band in range(5):
            group = [r for r in rows if min(4, int(r[model][index] * 5)) == band]
            bins.append({
                "band": band, "n": len(group),
                "mean_forecast": (math.fsum(r[model][index] for r in group) / len(group)
                                  if group else None),
                "observed_frequency": (
                    sum(r["y"] == index for r in group) / len(group) if group else None),
            })
        output.append({"side": name, "bins": bins})
    return output


def evaluate_paired(cases, *, evaluated_utc):
    """Require an entirely coherent distinct-fixture paired cohort (no dropna)."""
    evaluated = _clock(evaluated_utc)
    if type(cases) is not list or not 1 <= len(cases) <= MAX_PAIRED_FIXTURES:
        raise ValueError("INVALID_PAIRED_COLLECTION")
    rows = [_row(case, evaluated=evaluated) for case in cases]
    if len({r["fixture_id"] for r in rows}) != len(rows):
        raise ValueError("DUPLICATE_FIXTURE_OR_SNAPSHOT")
    if len({(r["baseline_id"], r["challenger_id"]) for r in rows}) != 1:
        raise ValueError("MIXED_MODEL_VERSIONS")
    rows.sort(key=lambda r: (r["kickoff"], r["fixture_id"]))
    if len(rows) < MIN_PAIRED_FIXTURES:
        raise ValueError("INSUFFICIENT_INDEPENDENT_FIXTURES")
    computed = {}
    for model in ("baseline", "challenger"):
        measure = [_score(r[model], r["y"]) for r in rows]
        computed[model] = {
            "mean_log_loss": math.fsum(x[0] for x in measure) / len(rows),
            "mean_brier": math.fsum(x[1] for x in measure) / len(rows),
            "mean_rps": math.fsum(x[2] for x in measure) / len(rows),
            "calibration": _calibration(rows, model),
        }
    return {
        "schema": SCHEMA, "status": "EXPLORATORY_ONLY",
        "cohort_n_independent_fixture_ids": len(rows),
        "model_ids": {"baseline": rows[0]["baseline_id"],
                      "challenger": rows[0]["challenger_id"]},
        "metric": computed,
        "paired_baseline_minus_challenger_log_loss": (
            computed["baseline"]["mean_log_loss"] - computed["challenger"]["mean_log_loss"]),
        "paired_baseline_minus_challenger_brier": (
            computed["baseline"]["mean_brier"] - computed["challenger"]["mean_brier"]),
        "self_asserted_cohort_hash": _hash(cases),
        "independent_result_authentication": False,
        "external_archive_clock_attestation": False,
        "true_prospective_holdout_verified": False,
        "model_accuracy_gain_verified": False,
        "ev_or_roi_verified": False,
        "model_promotable": False,
        "production_recommendations": "DISABLED",
    }


def audit_paired(cases, *, evaluated_utc):
    try:
        return evaluate_paired(cases, evaluated_utc=evaluated_utc)
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        return {
            "schema": SCHEMA, "status": "HOLD", "reason": str(exc) or "INVALID_INPUT",
            "model_accuracy_gain_verified": False, "ev_or_roi_verified": False,
            "model_promotable": False,
            "production_recommendations": "DISABLED",
        }


def audit_quote_metadata(quote, *, fixture_id, decision_utc, kickoff_utc):
    """Strict metadata check, always HOLD for executable-quote/EV certification.

    A self-described bookmaker or boolean certification cannot prove actual
    price executability, licensing or a synchronized price to a forecast.
    """
    base = {
        "schema": SCHEMA, "status": "HOLD", "quote_metadata_consistent": False,
        "market_executable_verified": False, "ev_or_roi_verified": False,
        "positive_ev_verified": False, "production_recommendations": "DISABLED",
    }
    try:
        if type(quote) is not dict or set(quote) != QUOTE_FIELDS:
            raise ValueError("INVALID_QUOTE_SCHEMA")
        if (not _id(fixture_id) or quote["fixture_id"] != fixture_id
                or not _id(quote["bookmaker"]) or not _id(quote["quote_id"])
                or not _sha(quote["raw_sha256"])
                or quote["scope"] != "REGULATION_90_MINUTES_INCLUDING_STOPPAGE"
                or quote["licensed_and_executable_independently_verified"] is not False):
            raise ValueError("UNATTESTED_QUOTE_OR_WRONG_SCOPE")
        market, side, line = quote["market"], quote["side"], quote["line"]
        if market not in ("h2h", "asian_handicap", "totals"):
            raise ValueError("INVALID_MARKET")
        if market == "h2h" and line is not None:
            raise ValueError("H2H_WITH_LINE")
        # Reuses PR-03's strict quarter-line and side validation.
        grade_score(0, 0, market=market, side=side, line=line)
        decimal_odds = quote["decimal_odds"]
        if (type(decimal_odds) not in (int, float)
                or not math.isfinite(decimal_odds) or not 1.01 <= decimal_odds <= 100):
            raise ValueError("INVALID_DECIMAL_ODDS")
        decision, kickoff = _clock(decision_utc), _clock(kickoff_utc)
        updated, captured, received, available = [
            _clock(quote[k]) for k in ("provider_updated_utc", "captured_utc",
                                      "received_utc", "available_utc")]
        if not updated <= captured <= received <= available <= decision:
            raise ValueError("FUTURE_OR_OUT_OF_ORDER_QUOTE")
        if (updated < kickoff - timedelta(days=7)
                or decision - updated > timedelta(minutes=5)):
            raise ValueError("STALE_QUOTE")
        return {
            **base, "quote_metadata_consistent": True,
            "reason": "METADATA_ONLY_NO_INDEPENDENT_EXECUTABILITY_OR_MODEL_CALIBRATION",
            "unverified_quote_digest": _hash(quote),
        }
    except (TypeError, KeyError, ValueError, OverflowError, InvalidOperation) as exc:
        return {**base, "reason": str(exc) or "INVALID_QUOTE"}
