"""One-GET real OpenLigaDB Bundesliga source -> unverified new goal shadow cohort.

This is not a self-authenticating independent evidence or market-odds feed.
Exactly one unmodified original V4.1 gateway GET feeds A's pre-kickoff
research rates and the previous-finished-result source-specific goal prior.
No previous post-match prediction is relabelled as new.
"""
import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from .forward_goal_shadow_cohort_seal import build, verify, SCHEMA
from .shadow_forecast import HK, _get_fixtures_with_native_inputs, predict_league

MAX_DAYS = 7
SOURCE_NAME = "OpenLigaDB"


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("MISSING_SOURCE_KICKOFF_TIME")
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_SOURCE_KICKOFF_TIME") from exc
    if d.tzinfo is None:
        raise ValueError("NAIVE_SOURCE_KICKOFF_TIME")
    return d.astimezone(timezone.utc)


def build_live_input(source, forecasts, *, source_received, model_computed,
                     model_sha, season, run_id):
    """Only uses SAME source GET, no outcomes from prospective fixture rows."""
    if (not isinstance(source, dict) or source.get("status") != "READY_RESEARCH"
            or source.get("source") != SOURCE_NAME
            or source.get("league") != "bundesliga"
            or source.get("season") != season
            or not isinstance(source.get("matches"), list)):
        raise ValueError("ORIGINAL_LIVE_SOURCE_NOT_READY")
    raw_hash = source.get("_same_response_source_sha256")
    if (type(raw_hash) is not str or len(raw_hash) != 64
            or raw_hash != source.get("sha256")):
        raise ValueError("ONE_GET_RAW_SOURCE_HASH_MISSING")
    if type(forecasts) is not list:
        raise ValueError("INVALID_ORIGINAL_FORECAST_OUTPUT")
    if type(source_received) is not datetime or source_received.tzinfo is None:
        raise ValueError("INVALID_SOURCE_OBSERVATION")
    if type(model_computed) is not datetime or model_computed.tzinfo is None:
        raise ValueError("INVALID_MODEL_OBSERVATION")

    # The FIXTURE UNIVERSE is every same-source normalized scheduled match
    # within the *declared fixed next 7 days*. No ranking, best-case filtering.
    # Any scheduled match with untrusted native identity aborts this capture.
    fixture_rows = []
    existing = set()
    cutoff = model_computed + timedelta(minutes=10)
    upper = model_computed + timedelta(days=MAX_DAYS)
    for row in source["matches"]:
        if not isinstance(row, dict) or row.get("status") != "SCHEDULED":
            continue
        ko = _utc(row.get("kickoff_utc"))
        if not cutoff <= ko <= upper:
            continue
        if row.get("score_ft") is not None:
            raise ValueError("SCHEDULED_SOURCE_ROW_CONTAINS_RESULT")
        native = row.get("_same_response_native_fixture_input")
        if (not isinstance(native, dict)
                or native.get("source_response_sha256") != raw_hash
                or native.get("league_shortcut") != "bl1"
                or native.get("match_id") is None
                or type(native.get("home_team_id")) is not int
                or type(native.get("away_team_id")) is not int):
            raise ValueError("SCHEDULED_NATIVE_FIXTURE_IDENTITY_UNVERIFIED")
        event_id = row.get("event_id")
        fid = "openligadb:" + str(native["match_id"])
        if event_id != fid or fid in existing:
            raise ValueError("DUPLICATE_OR_CONFLICTING_SCHEDULED_FIXTURE")
        existing.add(fid)
        fixture_rows.append({
            "fixture_id": fid, "home_team_id": str(native["home_team_id"]),
            "away_team_id": str(native["away_team_id"]),
            "kickoff_utc": ko.isoformat(),
        })
    if not fixture_rows:
        raise ValueError("NO_FRESH_UNSELECTED_SOURCE_FIXTURES")

    # Train prior derives from genuine finished same-response matches with
    # recorded kickoffs preceding the current local calendar day.
    # 'training_cutoff_utc' denotes latest INCLUDED finished match kickoff,
    # NOT independent source publication time. Original A obtains all valid
    # earlier results from this source via its unchanged predict_league API.
    seen_hist = {}
    for row in source["matches"]:
        if (not isinstance(row, dict) or row.get("status") != "FINISHED"
                or row.get("date", "") >= model_computed.astimezone(HK).date().isoformat()):
            continue
        score = row.get("score_ft")
        if type(score) is not list or len(score) != 2 or any(
                type(v) is not int or not 0 <= v <= 25 for v in score):
            continue
        try:
            ko = _utc(row.get("kickoff_utc"))
        except (ValueError, TypeError):
            continue
        if ko >= source_received:
            raise ValueError("HISTORICAL_KICKOFF_NOT_PRIOR_TO_RECEIPT")
        key = (row.get("date"), row.get("home"), row.get("away"))
        if key in seen_hist and seen_hist[key] != (ko, tuple(score)):
            raise ValueError("CONFLICTING_SOURCE_HISTORICAL_SCORE")
        seen_hist[key] = (ko, tuple(score))
    if len(seen_hist) < 30:
        raise ValueError("INSUFFICIENT_PAST_KICKOFF_RECORDS_FOR_PRIOR")
    actual = list(seen_hist.values())
    last_prior_match_kickoff = max(x[0] for x in actual)
    n = len(actual)
    over = (sum(sum(x[1]) > 2 for x in actual) + .5) / (n+1)
    btts = (sum(x[1][0] > 0 and x[1][1] > 0 for x in actual) + .5) / (n+1)

    pred_index = {}
    for row in forecasts:
        if not isinstance(row, dict) or not isinstance(row.get("event_id"), str):
            raise ValueError("BAD_ORIGINAL_MODEL_OUTPUT")
        fid = row["event_id"]
        if fid in pred_index:
            raise ValueError("DUPLICATE_ORIGINAL_MODEL_FORECAST")
        pred_index[fid] = row
    to_freeze = []
    for row in fixture_rows:
        p = pred_index.get(row["fixture_id"])
        if p is None:
            continue
        if p.get("kickoff_utc") is None or _utc(p["kickoff_utc"]) != _utc(row["kickoff_utc"]):
            raise ValueError("SOURCE_VS_MODEL_KICKOFF_CONFLICT")
        to_freeze.append({
            "fixture_id": row["fixture_id"],
            "model_revision_sha": model_sha,
            "computed_utc": model_computed.isoformat(),
            "expected_home_goals": p.get("expected_home_goals"),
            "expected_away_goals": p.get("expected_away_goals"),
        })
    payload = {
        "schema": SCHEMA,
        "production_recommendations": "DISABLED",
        "source": {
            "namespace": "openligadb", "league": "bundesliga",
            "source_response_sha256": raw_hash,
            "source_received_utc": source_received.isoformat(),
            "source_capture_id": run_id,
        },
        "training": {
            "league": "bundesliga", "training_source_sha256": raw_hash,
            "training_cutoff_utc": last_prior_match_kickoff.isoformat(),
            "training_match_count": n,
            "over25_frequency": over,
            "btts_frequency": btts,
        },
        "fixtures": fixture_rows,
        "forecasts": to_freeze,
    }
    return payload


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, help="Must not already exist")
    p.add_argument("--run-id", required=True)
    p.add_argument("--model-sha", required=True)
    args = p.parse_args(argv)
    # The original package MUST be unpacked and pinned by the calling
    # workflow. Never substitute an unverified generic Python model here.
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root / "app"))
    try:
        import fixture_gateway
    except ImportError as exc:
        raise ValueError("ORIGINAL_V41_GATEWAY_UNAVAILABLE") from exc
    requested_at = datetime.now(timezone.utc)
    hkt = requested_at.astimezone(HK)
    year = hkt.year if hkt.month >= 7 else hkt.year-1
    season = f"{year}-{(year+1)%100:02d}"
    result = _get_fixtures_with_native_inputs(
        season=season, league="bundesliga",
        clock=lambda: datetime.now(timezone.utc))
    source_received = datetime.now(timezone.utc)
    forecasts = predict_league(result["matches"], "bundesliga",
                               datetime.now(timezone.utc))
    model_computed = datetime.now(timezone.utc)
    live_input = build_live_input(
        result, forecasts, source_received=source_received,
        model_computed=model_computed, model_sha=args.model_sha,
        season=season, run_id=args.run_id)
    frozen = build(live_input)  # no override: actual current UTC clock
    verify(frozen)
    target = Path(args.output)
    if target.exists() or target.is_symlink():
        raise ValueError("FORWARD_FREEZE_OUTPUT_ALREADY_EXISTS")
    import os
    data = (json.dumps(frozen, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False)+"\n").encode()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    print("LIVE_OPENLIGA_GOAL_SHADOW_ONLY",
          frozen["sha256"], "fixtures",
          frozen["payload"]["source_fixture_universe_count"], "forecasts",
          frozen["payload"]["prematch_forecasts_present"],
          "HOLD DISABLED; SOURCE NOT INDEPENDENTLY ATTESTED")


if __name__ == "__main__":
    main()
