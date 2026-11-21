"""Offline byte-binding preflight for ONE claimed prospective football case.

Content equality and declared chronology are NOT independent provenance.
This module neither uses private keys nor treats a caller's verified=True flag
as trusted. PR #463 must independently replay a TSA token over the EXACT
manifest bytes; PR #464 needs genuine source-native FT result verification.
The report is ALWAYS HOLD / production DISABLED even on successful preflight.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re

SCHEMA = "football-king-first-case-byte-binding-v1"
FORECAST_SCHEMA = "football-king-first-case-forecast-v1"
QUOTE_SCHEMA = "football-king-first-case-quote-v1"
MANIFEST_SCHEMA = "football-king-first-case-manifest-v1"
MAX_BYTES = 1_000_000
MAX_QUOTE_AGE_SECONDS = 120
MIN_PREMATCH_BUFFER_MINUTES = 10
HEX = re.compile(r"[0-9a-f]{64}\Z")

FORECAST_KEYS = frozenset((
    "schema", "fixture_id", "league", "home_key", "away_key",
    "kickoff_utc", "captured_utc", "model_version",
    "probabilities_1x2", "production_recommendations",
))
QUOTE_KEYS = frozenset((
    "schema", "fixture_id", "league", "home_key", "away_key",
    "kickoff_utc", "provider", "provider_event_id", "market",
    "selection", "line", "observed_utc", "captured_utc",
    "decimal_odds", "production_recommendations",
))
MANIFEST_KEYS = frozenset((
    "schema", "fixture_id", "kickoff_utc", "forecast_sha256",
    "quote_sha256", "created_utc", "status", "production_recommendations",
))


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_FIELD")
        out[key] = value
    return out


def _reject_constant(_):
    raise ValueError("NONFINITE_JSON_CONSTANT")


def _read_json(raw, expected_fields, schema):
    if type(raw) is not bytes or not raw or len(raw) > MAX_BYTES:
        raise ValueError("INVALID_OR_OVERSIZED_SOURCE_BYTES")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                         parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("INVALID_SOURCE_JSON") from exc
    if (type(doc) is not dict or set(doc) != expected_fields
            or doc.get("schema") != schema
            or doc.get("production_recommendations") != "DISABLED"):
        raise ValueError("INVALID_EVIDENCE_SCHEMA_OR_RELEASE_FLAG")
    return doc


def _time(value):
    if type(value) is not str or not 10 <= len(value) <= 50:
        raise ValueError("INVALID_TIMESTAMP")
    try:
        point = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if point.tzinfo is None or point.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return point.astimezone(timezone.utc)


def _name(value):
    if (type(value) is not str or not 1 <= len(value.strip()) <= 120
            or value != value.strip()):
        raise ValueError("INVALID_CASE_IDENTITY")
    return value


def _num(value, low, high):
    return type(value) in (int, float) and math.isfinite(value) and low <= value <= high


def _market(quote):
    market, selection, line = quote["market"], quote["selection"], quote["line"]
    if market == "h2h":
        if selection not in ("HOME", "DRAW", "AWAY") or line is not None:
            raise ValueError("MARKET_DIRECTION_LINE_MISMATCH")
    elif market == "spreads":
        if (selection not in ("HOME", "AWAY")
                or not _num(line, -10, 10)
                or abs(line * 4 - round(line * 4)) > 1e-9):
            raise ValueError("MARKET_DIRECTION_LINE_MISMATCH")
    elif market == "totals":
        if (selection not in ("OVER", "UNDER")
                or not _num(line, .25, 15)
                or abs(line * 4 - round(line * 4)) > 1e-9):
            raise ValueError("MARKET_DIRECTION_LINE_MISMATCH")
    else:
        raise ValueError("UNSUPPORTED_MARKET")


def inspect(forecast_raw, quote_raw, manifest_raw):
    """Validate byte hashes, claimed fixture binding and chronology in memory."""
    forecast = _read_json(forecast_raw, FORECAST_KEYS, FORECAST_SCHEMA)
    quote = _read_json(quote_raw, QUOTE_KEYS, QUOTE_SCHEMA)
    manifest = _read_json(manifest_raw, MANIFEST_KEYS, MANIFEST_SCHEMA)
    if manifest["status"] != "HOLD":
        raise ValueError("MANIFEST_MUST_BE_HOLD")
    for name in ("fixture_id", "league", "home_key", "away_key"):
        items = [forecast[name], quote[name]]
        if name == "fixture_id":
            items.append(manifest[name])
        if any(_name(item) != items[0] for item in items):
            raise ValueError("CROSS_SOURCE_IDENTITY_CLAIM_MISMATCH")
    if forecast["home_key"] == forecast["away_key"]:
        raise ValueError("SAME_HOME_AWAY_KEY")
    for name in ("model_version",):
        _name(forecast[name])
    for name in ("provider", "provider_event_id"):
        _name(quote[name])
    _market(quote)
    p = forecast["probabilities_1x2"]
    if (type(p) is not list or len(p) != 3
            or any(not _num(x, 0, 1) for x in p)
            or abs(math.fsum(p) - 1) > 1e-8):
        raise ValueError("INVALID_FORECAST_1X2_PROBABILITIES")
    if not _num(quote["decimal_odds"], 1.01, 100):
        raise ValueError("INVALID_CLAIMED_PRICE")
    if (type(manifest["forecast_sha256"]) is not str
            or type(manifest["quote_sha256"]) is not str
            or not HEX.fullmatch(manifest["forecast_sha256"])
            or not HEX.fullmatch(manifest["quote_sha256"])):
        raise ValueError("INVALID_DIGEST_FORMAT")
    forecast_sha = hashlib.sha256(forecast_raw).hexdigest()
    quote_sha = hashlib.sha256(quote_raw).hexdigest()
    if (manifest["forecast_sha256"] != forecast_sha
            or manifest["quote_sha256"] != quote_sha):
        raise ValueError("RAW_BYTES_DIGEST_MISMATCH")
    kickoff = _time(forecast["kickoff_utc"])
    if (_time(quote["kickoff_utc"]) != kickoff
            or _time(manifest["kickoff_utc"]) != kickoff):
        raise ValueError("CROSS_SOURCE_KICKOFF_CLAIM_MISMATCH")
    observed = _time(quote["observed_utc"])
    quote_captured = _time(quote["captured_utc"])
    forecast_captured = _time(forecast["captured_utc"])
    manifest_created = _time(manifest["created_utc"])
    if not (observed <= quote_captured <= forecast_captured <= manifest_created
            <= kickoff - timedelta(minutes=MIN_PREMATCH_BUFFER_MINUTES)):
        raise ValueError("LOOKAHEAD_OR_INVALID_CAPTURE_ORDER")
    if (quote_captured - observed).total_seconds() > MAX_QUOTE_AGE_SECONDS:
        raise ValueError("STALE_CLAIMED_QUOTE")
    # The observation must remain fresh at the *final sealed-manifest time*,
    # not merely when a possibly hour-old quote was first copied. The same
    # 120-second window also constrains the forecast-to-seal lifetime.
    if (manifest_created - observed).total_seconds() > MAX_QUOTE_AGE_SECONDS:
        raise ValueError("QUOTE_STALE_AT_FORECAST_SEAL")

    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "BYTE_AND_DECLARED_CHRONOLOGY_CONSISTENT_NOT_INDEPENDENTLY_VERIFIED",
        "fixture_id_claim": forecast["fixture_id"],
        "market_claim": quote["market"],
        "forecast_sha256": forecast_sha,
        "quote_sha256": quote_sha,
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "byte_digest_binding_checked": True,
        "declared_prematch_time_order_checked": True,
        "fixture_identity_claims_consistent": True,
        "fixture_identity_source_native_authenticated": False,
        "forecast_capture_time_independently_authenticated": False,
        "timestamp_token_verified_for_manifest_here": False,
        "tsa_trust_policy_verified": False,
        "market_quote_executable_authenticated": False,
        "independent_second_ft_source_authenticated": False,
        "regulation_ft_settlement_authenticated": False,
        "certified_forward_case_count": 0,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
        "model_promotion_allowed": False,
        "recommended_stake": None,
        "production_recommendations": "DISABLED",
        "blockers": [
            "EXTERNAL_TSA_TOKEN_AND_TRUST_POLICY_REQUIRED",
            "SOURCE_NATIVE_IDENTITY_REVIEW_REQUIRED",
            "EXECUTABLE_MARKET_QUOTE_NOT_AUTHENTICATED",
            "TWO_INDEPENDENT_SOURCE_NATIVE_FT_REPORTS_REQUIRED",
            "PAIRED_FORWARD_COHORT_NOT_INDEPENDENTLY_VALIDATED",
        ],
    }


def audit(forecast_raw, quote_raw, manifest_raw):
    """Fail closed and never return raw prices, probability vectors or betting picks."""
    try:
        return inspect(forecast_raw, quote_raw, manifest_raw)
    except (ValueError, TypeError, OverflowError) as exc:
        return {
            "schema": SCHEMA,
            "status": "HOLD",
            "reason": str(exc),
            "byte_digest_binding_checked": False,
            "certified_forward_case_count": 0,
            "eligible_for_model_scoring": False,
            "positive_ev_verified": False,
            "model_promotion_allowed": False,
            "recommended_stake": None,
            "production_recommendations": "DISABLED",
        }


def _read_file(path):
    p = Path(path)
    if (not p.is_file() or p.is_symlink()
            or p.stat().st_size == 0 or p.stat().st_size > MAX_BYTES):
        raise ValueError("UNSAFE_OR_OVERSIZED_EVIDENCE_FILE")
    data = p.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError("UNSAFE_OR_OVERSIZED_EVIDENCE_FILE")
    return data


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecast", required=True)
    parser.add_argument("--quote", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(_read_file(args.forecast), _read_file(args.quote),
                       _read_file(args.manifest))
    except (ValueError, OSError) as exc:
        report = {"schema": SCHEMA, "status": "HOLD",
                  "reason": str(exc) if type(exc) is ValueError else "FILE_READ_FAILED",
                  "certified_forward_case_count": 0,
                  "eligible_for_model_scoring": False,
                  "positive_ev_verified": False,
                  "production_recommendations": "DISABLED"}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if not report.get("byte_digest_binding_checked"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
