"""Offline bridge from pinned native shadow archive to VNext prematch schema.
Only the explicit joint Poisson rates are transferred, never ensemble 1X2.
Archive hash, clocks and native IDs are structural checks, not authentication.
"""
import hashlib
import hmac
import json
from datetime import timedelta
from inplay_state_challenger_vnext import _clock, _rate, _valid_digest

MAX_BYTES = 3_000_000
MODELS = {
    "bl1": ("bundesliga", "v5-seven-model-native-bundesliga-shadow-v1"),
    "bl2": ("bundesliga2", "v5-1-seven-model-native-bl2-shadow-v1"),
    "bl3": ("germany_liga3", "v5-1-seven-model-native-bl3-shadow-v1"),
}

def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result

def _nonfinite(_):
    raise ValueError("NONFINITE_JSON")

def _native(value):
    if (type(value) is not str or not 1 <= len(value) <= 19
            or not value.isascii() or not value.isdecimal()
            or not 0 < int(value) < 2**63 or str(int(value)) != value):
        raise ValueError("INVALID_NATIVE_ID")
    return value

def build_prematch(raw, expected_sha256, *, fixture_id, home_native_id,
                   away_native_id, kickoff_utc):
    """Return the existing VNext prematch payload or raise; no live I/O."""
    if (type(raw) is not bytes or not 0 < len(raw) <= MAX_BYTES
            or not _valid_digest(expected_sha256)
            or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256)):
        raise ValueError("ARCHIVE_COMMITMENT_MISMATCH")
    doc = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
    if type(doc) is not dict or doc.get("schema") != "v5-native-forward-shadow-v1":
        raise ValueError("UNSUPPORTED_ARCHIVE_SCHEMA")
    shortcut = doc.get("provider_league_shortcut")
    if type(shortcut) is not str or shortcut not in MODELS:
        raise ValueError("UNSUPPORTED_LEAGUE")
    league, model = MODELS[shortcut]
    if (doc.get("provider") != "OpenLigaDB" or doc.get("league") != league
            or doc.get("model_id") != model or doc.get("status") != "SHADOW_ONLY"
            or doc.get("production_recommendations") != "DISABLED"
            or type(doc.get("verified_forward_sample_credit")) is not int
            or doc["verified_forward_sample_credit"] != 0
            or any(doc.get(k) is not False for k in (
                "source_independent", "result_authentication",
                "external_capture_witness_verified",
                "feature_availability_independently_verified",
                "market_odds_available", "automatic_promotion"))):
        raise ValueError("UNSUPPORTED_ARCHIVE_STATE")
    if type(fixture_id) is not str or not fixture_id.startswith("openligadb:"):
        raise ValueError("INVALID_FIXTURE_NAMESPACE")
    event = _native(fixture_id[len("openligadb:"):])
    home, away = _native(home_native_id), _native(away_native_id)
    if home == away:
        raise ValueError("INVALID_TEAM_IDS")
    kickoff = _clock(kickoff_utc)
    rows = doc.get("predictions")
    if (type(rows) is not list or not 1 <= len(rows) <= 400
            or type(doc.get("predictions_count")) is not int
            or doc["predictions_count"] != len(rows)
            or any(type(r) is not dict for r in rows)):
        raise ValueError("INVALID_ARCHIVE_ROWS")
    ids = [_native(r.get("provider_event_id")) for r in rows]
    if len(ids) != len(set(ids)) or event not in ids:
        raise ValueError("MISSING_OR_DUPLICATE_FIXTURE")
    row = rows[ids.index(event)]
    if (row.get("home_native_id") != home or row.get("away_native_id") != away
            or _clock(row.get("kickoff_utc")) != kickoff
            or row.get("production_recommendations") != "DISABLED"
            or row.get("joint_rates_are_not_ensemble_goal_distribution") is not True):
        raise ValueError("FIXTURE_OR_RATE_IDENTITY_MISMATCH")
    forecast = _clock(row.get("prediction_utc"))
    generated = _clock(doc.get("generated_utc"))
    receipts = doc.get("source_receipts")
    if (type(receipts) is not list or len(receipts) != 2
            or any(type(r) is not dict or not _valid_digest(r.get("sha256")) for r in receipts)):
        raise ValueError("INVALID_SOURCE_RECEIPTS")
    available = max(_clock(r.get("captured_utc")) for r in receipts)
    if not available <= forecast <= generated <= kickoff - timedelta(minutes=10):
        raise ValueError("ARCHIVE_CLOCK_ORDER")
    rates = row.get("joint_goal_rates")
    if type(rates) is not list or len(rates) != 2:
        raise ValueError("MISSING_EXPLICIT_JOINT_RATES")
    h, a = map(_rate, rates)
    return {"fixture_id": fixture_id, "model_id": model + ":joint-poisson-only",
            "forecast_utc": forecast.isoformat(),
            "inputs_available_utc": available.isoformat(),
            "expected_home_goals": h, "expected_away_goals": a,
            "input_sha256": expected_sha256, "calibrated": False,
            "production_recommendations": "DISABLED"}
