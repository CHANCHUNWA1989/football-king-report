"""Strict read-only prospective OU2.5/BTTS *research* cohort freeze gate.

Freezes all source-listed fixtures, including ones lacking model predictions;
DOES NOT retrieve or authenticate any source itself. Caller must supply a real,
fresh, source-identity-preserving input from a separate live capture. Source,
timestamps, results, identifiers and previous-season prior are SELF-REPORTED.
Hashing cannot independently attest the true original publication time.

This tool cannot accept outcomes, odds or claims of certified bet value.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re

SCHEMA = "football-king-forward-goal-shadow-cohort-v1"
BLEND = 0.25
MAX_FIXTURES = 100
MIN_TRAINING = 30
MIN_KICKOFF_BUFFER = timedelta(minutes=10)
MAX_SOURCE_AGE = timedelta(minutes=30)


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _fields(value, names, code):
    _require(isinstance(value, dict) and set(value) == set(names), code)


def _string(value, code, limit=140):
    _require(type(value) is str and 0 < len(value.strip()) <= limit
             and value == value.strip(), code)
    return value


def _instant(value):
    _require(type(value) is str and 0 < len(value) <= 60, "INVALID_TIMESTAMP")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    _require(stamp.tzinfo is not None and stamp.utcoffset() is not None,
             "NAIVE_TIMESTAMP")
    return stamp.astimezone(timezone.utc)


def _sha(value, reason):
    _require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None,
             reason)
    return value


def _git_sha(value):
    _require(type(value) is str and re.fullmatch("[0-9a-f]{40}", value) is not None,
             "INVALID_MODEL_SOURCE_COMMIT")


def _number(value, label, lo, hi):
    _require(type(value) in (int, float) and math.isfinite(value)
             and lo <= value <= hi, label)
    return float(value)


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def build(payload, *, now=None):
    """Compute a future-only exploratory digest; never certify a prospective sample.

    'now' is injectable solely for deterministic offline testing. The CLI
    always calls without this parameter, using the actual runner UTC clock.
    """
    _fields(payload, ("schema", "production_recommendations", "source",
                      "training", "fixtures", "forecasts"), "INVALID_INPUT_CONTRACT")
    _require(payload["schema"] == SCHEMA
             and payload["production_recommendations"] == "DISABLED",
             "UNSAFE_RECOMMENDATION_CONTRACT")
    now = now if now is not None else datetime.now(timezone.utc)
    _require(isinstance(now, datetime) and now.tzinfo is not None,
             "INVALID_CAPTURE_CLOCK")
    now = now.astimezone(timezone.utc)

    source = payload["source"]
    _fields(source, ("namespace", "league", "source_response_sha256",
                     "source_received_utc", "source_capture_id"),
            "INVALID_SOURCE_METADATA")
    namespace = _string(source["namespace"], "INVALID_SOURCE_NAMESPACE")
    league = _string(source["league"], "INVALID_LEAGUE")
    _sha(source["source_response_sha256"], "INVALID_SOURCE_HASH")
    _string(source["source_capture_id"], "INVALID_SOURCE_CAPTURE_ID")
    received = _instant(source["source_received_utc"])
    _require(received <= now and now-received <= MAX_SOURCE_AGE,
             "SOURCE_CAPTURE_STALE_OR_FUTURE")

    training = payload["training"]
    _fields(training, ("league", "training_source_sha256", "training_cutoff_utc",
                       "training_match_count", "over25_frequency", "btts_frequency"),
            "INVALID_TRAINING_METADATA")
    _require(training["league"] == league, "TRAINING_LEAGUE_MISMATCH")
    _sha(training["training_source_sha256"], "INVALID_TRAINING_HASH")
    cutoff = _instant(training["training_cutoff_utc"])
    _require(cutoff < received, "TRAINING_CUTOFF_NOT_BEFORE_SOURCE")
    _require(type(training["training_match_count"]) is int
             and training["training_match_count"] >= MIN_TRAINING,
             "INSUFFICIENT_TRAINING_EVIDENCE")
    over_prior = _number(training["over25_frequency"], "INVALID_TRAINING_PRIOR", 0, 1)
    btts_prior = _number(training["btts_frequency"], "INVALID_TRAINING_PRIOR", 0, 1)

    fixtures, forecasts = payload["fixtures"], payload["forecasts"]
    _require(type(fixtures) is list and 1 <= len(fixtures) <= MAX_FIXTURES,
             "INVALID_FIXTURE_UNIVERSE")
    _require(type(forecasts) is list and len(forecasts) <= MAX_FIXTURES,
             "INVALID_FORECAST_SET")
    cohort = {}
    for row in fixtures:
        _fields(row, ("fixture_id", "home_team_id", "away_team_id", "kickoff_utc"),
                "INVALID_FIXTURE_CONTRACT")
        fid = _string(row["fixture_id"], "INVALID_FIXTURE_ID")
        _require(fid.startswith(namespace + ":"), "FIXTURE_SOURCE_ID_MISMATCH")
        home = _string(row["home_team_id"], "INVALID_NATIVE_TEAM_ID")
        away = _string(row["away_team_id"], "INVALID_NATIVE_TEAM_ID")
        _require(home != away and fid not in cohort,
                 "DUPLICATE_FIXTURE_OR_TEAM_ID")
        kickoff = _instant(row["kickoff_utc"])
        _require(now <= kickoff - MIN_KICKOFF_BUFFER,
                 "LATE_OR_STARTED_FIXTURE_IN_UNIVERSE")
        cohort[fid] = {"identity": row, "kickoff": kickoff}

    forecasts_by_id = {}
    model_revision = None
    for row in forecasts:
        _fields(row, ("fixture_id", "model_revision_sha", "computed_utc",
                      "expected_home_goals", "expected_away_goals"),
                "INVALID_FORECAST_CONTRACT")
        fid = _string(row["fixture_id"], "INVALID_FORECAST_ID")
        _require(fid in cohort and fid not in forecasts_by_id,
                 "DUPLICATE_OR_UNLISTED_FORECAST")
        _git_sha(row["model_revision_sha"])
        if model_revision is None:
            model_revision = row["model_revision_sha"]
        _require(model_revision == row["model_revision_sha"],
                 "MIXED_MODEL_REVISIONS")
        model_at = _instant(row["computed_utc"])
        _require(received <= model_at <= now
                 and model_at <= cohort[fid]["kickoff"] - MIN_KICKOFF_BUFFER,
                 "FORECAST_NOT_FRESH_PREMATCH")
        _number(row["expected_home_goals"], "INVALID_ORIGINAL_GOAL_RATES", .1, 5.5)
        _number(row["expected_away_goals"], "INVALID_ORIGINAL_GOAL_RATES", .1, 5.5)
        forecasts_by_id[fid] = row

    results = []
    for fid in sorted(cohort):
        entry = cohort[fid]
        raw = forecasts_by_id.get(fid)
        if raw is None:
            results.append({
                "fixture": entry["identity"], "state": "HOLD_NO_PREMATCH_MODEL",
                "original_a_rates": None, "over25": None, "btts": None,
            })
            continue
        h = float(raw["expected_home_goals"])
        a = float(raw["expected_away_goals"])
        total = h + a
        model_over = 1.0 - math.exp(-total) * (1 + total + total * total / 2)
        model_btts = (1-math.exp(-h))*(1-math.exp(-a))
        results.append({
            "fixture": entry["identity"],
            "state": "UNVERIFIED_PREMATCH_RESEARCH_FORECAST",
            "model_computed_utc": raw["computed_utc"],
            "original_a_rates": {"home": h, "away": a},
            "over25": {
                "original": model_over,
                "training_only_prior": over_prior,
                "exploratory_75_25_blend": (1-BLEND)*model_over + BLEND*over_prior,
            },
            "btts": {
                "original": model_btts,
                "training_only_prior": btts_prior,
                "exploratory_75_25_blend": (1-BLEND)*model_btts + BLEND*btts_prior,
            },
        })
    report = {
        "schema": SCHEMA,
        "status": "HOLD",
        "research_only": True,
        "source": source,
        "training": training,
        "source_fixture_universe_count": len(fixtures),
        "prematch_forecasts_present": len(forecasts_by_id),
        "missing_forecasts_included_as_holds": len(fixtures)-len(forecasts_by_id),
        "captured_by_local_runner_utc_self_reported": now.isoformat(),
        "original_model_revision_sha": model_revision,
        "fixed_blend_weight": BLEND,
        "fixtures": results,
        "future_results_used_to_fit": False,
        "historical_exploratory_weight_not_future_verified": True,
        "source_and_capture_times_independently_attested": False,
        "source_fixture_ids_independently_authenticated": False,
        "raw_source_bytes_stored_or_attested": False,
        "training_inputs_independently_authenticated": False,
        "signed_prematch_forecast_verified": False,
        "certified_prospective_samples": 0,
        "actual_bookmaker_quotes_verified": False,
        "positive_ev_verified": False,
        "eligible_for_model_promotion": False,
        "production_recommendations": "DISABLED",
    }
    return {"payload": report, "sha256": hashlib.sha256(_canonical(report)).hexdigest()}


def verify(envelope):
    _fields(envelope, ("payload", "sha256"), "INVALID_ENVELOPE")
    _sha(envelope["sha256"], "INVALID_ENVELOPE_HASH")
    _require(hashlib.sha256(_canonical(envelope["payload"])).hexdigest()
             == envelope["sha256"], "COHORT_ENVELOPE_TAMPERED")
    p = envelope["payload"]
    _require(p["production_recommendations"] == "DISABLED"
             and p["status"] == "HOLD"
             and p["eligible_for_model_promotion"] is False
             and p["certified_prospective_samples"] == 0
             and p["signed_prematch_forecast_verified"] is False,
             "UNSAFE_ENVELOPE_FLAGS")
    return True


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, help="Source-native live capture, NOT historic backfill")
    p.add_argument("--output", required=True, help="Must not already exist")
    a = p.parse_args(argv)
    payload = json.loads(Path(a.input).read_text(encoding="utf-8"))
    envelope = build(payload)  # actual runner clock: cannot be backdated by file
    verify(envelope)
    destination = Path(a.output)
    if destination.exists() or destination.is_symlink():
        raise ValueError("COHORT_SNAPSHOT_ALREADY_EXISTS")
    encoded = _canonical(envelope) + b"\n"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as fp:
        fp.write(encoded)
        fp.flush()
        os.fsync(fp.fileno())
    print("FORWARD_GOAL_SHADOW", envelope["sha256"],
          envelope["payload"]["prematch_forecasts_present"],
          envelope["payload"]["missing_forecasts_included_as_holds"],
          "HOLD DISABLED")


if __name__ == "__main__":
    main()
