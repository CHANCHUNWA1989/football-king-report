"""Create-only private prematch manifest from already captured original bytes.

Only a fresh *local current UTC clock* supplies the manifest timestamp;
caller-provided capture/source timestamps remain untrusted claims. This is
neither a market quote collector nor a trusted TSA; an independent RFC3161
token over the exact output bytes is required afterwards.
Never commits or emits raw odds/probabilities to the public repository.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path

from first_case_payload_binding import (
    FORECAST_KEYS, FORECAST_SCHEMA, QUOTE_KEYS, QUOTE_SCHEMA,
    MANIFEST_SCHEMA, MAX_QUOTE_AGE_SECONDS, MIN_PREMATCH_BUFFER_MINUTES,
    _read_json, _read_file, _time, audit,
)

SCHEMA = "football-king-first-case-fresh-manifest-capture-v1"


def build(forecast_raw, quote_raw, *, now=None):
    """Build exact digest pins, rejecting late/stale self-claimed observations."""
    when = datetime.now(timezone.utc) if now is None else now
    if type(when) is not datetime or when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("INVALID_CAPTURE_CLOCK")
    when = when.astimezone(timezone.utc)
    f = _read_json(forecast_raw, FORECAST_KEYS, FORECAST_SCHEMA)
    q = _read_json(quote_raw, QUOTE_KEYS, QUOTE_SCHEMA)
    forecast_time = _time(f["captured_utc"])
    observed = _time(q["observed_utc"])
    captured = _time(q["captured_utc"])
    kickoff = _time(f["kickoff_utc"])

    # A claimed source timestamp does NOT authenticate itself. This simply
    # rejects any input that is already too old at the real runtime clock.
    if not (observed <= captured <= forecast_time <= when
            <= kickoff - timedelta(minutes=MIN_PREMATCH_BUFFER_MINUTES)):
        raise ValueError("LIVE_CAPTURE_OR_KICKOFF_CHRONOLOGY_INVALID")
    age = (when - observed).total_seconds()
    if age < 0 or age > MAX_QUOTE_AGE_SECONDS:
        raise ValueError("LIVE_QUOTE_NO_LONGER_FRESH")
    if (when - forecast_time).total_seconds() > MAX_QUOTE_AGE_SECONDS:
        raise ValueError("LIVE_FORECAST_NO_LONGER_FRESH")

    # No caller-supplied created_utc; the local clock is the only input.
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "fixture_id": f["fixture_id"],
        "kickoff_utc": f["kickoff_utc"],
        "forecast_sha256": hashlib.sha256(forecast_raw).hexdigest(),
        "quote_sha256": hashlib.sha256(quote_raw).hexdigest(),
        "created_utc": when.isoformat().replace("+00:00", "Z"),
        "status": "HOLD",
        "production_recommendations": "DISABLED",
    }
    original = (json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False)+"\n").encode("utf-8")
    report = audit(forecast_raw, quote_raw, original)
    if not report.get("byte_digest_binding_checked"):
        raise ValueError("LIVE_SOURCE_PAIR_REJECTED:" + report["reason"])
    return original, report


def create(forecast_file, quote_file, manifest_output, *, now=None):
    """Create, never replace: private manifest only, with mode 0600."""
    forecast_file = Path(forecast_file)
    quote_file = Path(quote_file)
    output = Path(manifest_output)
    if (output in (forecast_file, quote_file) or
            output.is_symlink() or output.exists() or
            not output.parent.is_dir() or output.parent.is_symlink()):
        raise ValueError("UNSAFE_OR_EXISTING_MANIFEST_OUTPUT")
    original_forecast, original_quote = (
        _read_file(forecast_file), _read_file(quote_file))
    raw, report = build(original_forecast, original_quote, now=now)
    # Recheck source originals before writing. No partial manifest is created
    # if either source is changed between calculation and the final handoff.
    if (_read_file(forecast_file) != original_forecast or
            _read_file(quote_file) != original_quote):
        raise ValueError("SOURCE_ORIGINAL_CHANGED_DURING_CAPTURE")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(output, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "FRESH_LOCAL_MANIFEST_CREATED_NOT_INDEPENDENTLY_TIMESTAMPED",
        "fixture_id_claim": report["fixture_id_claim"],
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "byte_digest_binding_checked": True,
        "local_clock_capture_only_not_independent_tsa": True,
        "model_source_authenticity_verified": False,
        "market_quote_executable_authenticated": False,
        "certified_forward_case_count": 0,
        "eligible_for_model_scoring": False,
        "positive_ev_verified": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forecast", required=True)
    parser.add_argument("--quote", required=True)
    parser.add_argument("--manifest-output", required=True)
    args = parser.parse_args(argv)
    try:
        result = create(args.forecast, args.quote, args.manifest_output)
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        result = {
            "schema": SCHEMA, "status": "HOLD",
            "reason": (str(exc) if isinstance(exc, ValueError) else
                       "LOCAL_CAPTURE_FAILED"),
            "certified_forward_case_count": 0,
            "eligible_for_model_scoring": False,
            "production_recommendations": "DISABLED",
        }
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    if not result.get("byte_digest_binding_checked"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
