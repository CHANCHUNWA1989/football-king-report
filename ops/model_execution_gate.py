"""Mandatory fail-closed execution receipt for genuine original A code invocations.

The only supported six leagues come directly from ops/shadow_forecast.py.
The caller must supply actual original normalized fixture/history rows, not
a quote or an xG screenshot. The original A prediction function is invoked
in this process; a missing/unsupported event emits NO prediction. An execution
receipt is evidence of software execution only, NOT proof that source rows,
match identity, result, or current odds were independently authenticated.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from shadow_forecast import LEAGUES, predict_league

SCHEMA = "football-king-model-execution-receipt-v1"
MODEL = "original-A-poisson-shrinkage-unvalidated-v4.1"
MAX_INPUT_ROWS = 6000


def _hold(league, event_id, reason):
    return {
        "schema": SCHEMA,
        "league": league,
        "source_event_id_unverified": event_id,
        "status": "HOLD",
        "reason": reason,
        "model_executed": False,
        "model_name": MODEL,
        "model_probabilities": None,
        "expected_goals": None,
        "training_observations_sha256": None,
        "execution_source_sha256": None,
        "as_of_utc": None,
        "source_fixture_identity_verified": False,
        "provider_capture_authenticated": False,
        "execution_time_externally_attested": False,
        "model_calibrated": False,
        "true_live_match_model_validated": False,
        "independent_result_verified": False,
        "verified_market_prices": False,
        "verified_positive_ev": False,
        "betting_eligible": False,
        "production_recommendations": "DISABLED",
    }


def _is_valid_probabilities(p):
    return (type(p) is list and len(p) == 3
            and all(type(v) in (float, int) and math.isfinite(v)
                    and 0 < v < 1 for v in p)
            and abs(math.fsum(p) - 1) < 1e-5)


def execute(rows, *, league, event_id, now):
    """Execute the original mathematical model, or return explicit HOLD.

    If invoked with synthetic/untrusted rows, a successful run is still
    **unverified research**, not an authenticated real live forecast.
    """
    out = _hold(league, event_id, "NOT_RUN")
    if type(league) is not str or league not in LEAGUES:
        out["reason"] = "MODEL_UNAVAILABLE_UNSUPPORTED_LEAGUE"
        return out
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        out["reason"] = "INVALID_OR_NAIVE_RUN_CLOCK"
        return out
    if (type(event_id) is not str or not 4 <= len(event_id) <= 128
            or event_id != event_id.strip()):
        out["reason"] = "MISSING_OR_INVALID_SOURCE_EVENT_ID"
        return out
    if type(rows) is not list or not 1 <= len(rows) <= MAX_INPUT_ROWS:
        out["reason"] = "MISSING_OR_INVALID_FIXTURE_HISTORY_INPUT"
        return out
    # Explicit event IDs are mandatory. Name/fuzzy/synthetic fallback IDs
    # generated inside the legacy model are NOT a certified matching key.
    candidates = [r for r in rows if type(r) is dict
                  and r.get("event_id") == event_id]
    if len(candidates) != 1:
        out["reason"] = "DUPLICATE_OR_UNMATCHED_SOURCE_EVENT_ID"
        return out
    raw = candidates[0]
    if raw.get("status") != "SCHEDULED" or raw.get("score_ft") is not None:
        out["reason"] = "NO_CLEAN_PREMATCH_SOURCE_FIXTURE"
        return out
    now = now.astimezone(timezone.utc)
    try:
        original = predict_league(rows, league, now)
    except (ValueError, KeyError, TypeError, OverflowError, ArithmeticError):
        out["reason"] = "ORIGINAL_MODEL_EXECUTION_FAILED"
        return out
    matched = [p for p in original if p.get("event_id") == event_id]
    if len(matched) != 1:
        out["reason"] = "NO_ELIGIBLE_ORIGINAL_MODEL_FORECAST"
        return out
    row = matched[0]
    p = [row.get(k) for k in ("p_home", "p_draw", "p_away")]
    if (row.get("production_recommendations") != "DISABLED"
            or row.get("calibrated") is not False
            or row.get("prediction_utc") != now.isoformat()
            or not _is_valid_probabilities(p)):
        out["reason"] = "UNSAFE_OR_MALFORMED_MODEL_OUTPUT"
        return out
    try:
        source_hash = hashlib.sha256(
            Path(__file__).with_name("shadow_forecast.py").read_bytes()
        ).hexdigest()
    except OSError:
        out["reason"] = "MISSING_MODEL_SOURCE"
        return out
    # Hashing the input does NOT prove authentic provenance or raw publisher bytes.
    try:
        input_hash = hashlib.sha256(json.dumps(
            rows, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError, OverflowError):
        out["reason"] = "INVALID_MODEL_INPUT_ENCODING"
        return out
    out.update({
        "status": "EXECUTED_RESEARCH_ONLY",
        "reason": "MODEL_EXECUTED_BUT_ORIGIN_AND_LIVE_CONTEXT_UNVERIFIED",
        "model_executed": True,
        "model_name": row.get("model"),
        "as_of_utc": now.isoformat(),
        "model_probabilities": p,
        "expected_goals": {
            "home": row["expected_home_goals"],
            "away": row["expected_away_goals"],
        },
        "training_games": row["training_games"],
        "training_observations_sha256": row["training_observations_sha256"],
        "normalized_input_sha256_not_source_attestation": input_hash,
        "execution_source_sha256": source_hash,
        "model_source_ref": "ops/shadow_forecast.py:predict_league",
    })
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Execute original model or show explicit unsupported/missing HOLD")
    parser.add_argument("--league", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--input", help="Original normalized fixture/history JSON list")
    parser.add_argument("--output", help="Optional receipt path")
    args = parser.parse_args(argv)
    rows = None
    if args.input:
        try:
            path = Path(args.input)
            if path.stat().st_size <= 8_000_000:
                rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, RecursionError):
            rows = None
    result = execute(rows, league=args.league, event_id=args.event_id,
                     now=datetime.now(timezone.utc))
    packed = json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(packed, encoding="utf-8")
    print(packed, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
