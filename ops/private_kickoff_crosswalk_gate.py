"""Two-publisher, private PREMATCH schedule crosswalk with no EV promotion.

This only checks LOCAL, time-claimed, separately supplied normalized schedule
observations. Provider names, snapshots, crosswalk IDs and recorded clocks are
self-asserted unless independently authenticated out of band. Distinct names
do NOT establish independent publishers or independently verified kickoff.

Never import results, forecast outcomes, public recommendations or prices.
No network access, data scraping, paid API credit or public fixture export.
"""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from private_quote_snapshot_receipt import (
    ReceiptError, _pairs_unique, _nonfinite, _utc, _read_raw_file,
    _payload_receipt, _write_private_new,
)
from private_quote_fixture_binding import _exact_id, _instant
from private_quote_forward_freeze import (
    FreezeError, _json_bytes_object, verify_freeze,
)

SCHEMA = "football-king-private-two-schedule-kickoff-crosswalk-v1"
EXPECTED_SOURCES = 2
MAX_SOURCE_BYTES = 1_000_000
MAX_SOURCE_EVENTS = 500
MAX_CAPTURE_AGE = timedelta(hours=6)
MAX_TIME_EARLY = timedelta(minutes=10)
SOURCE_NAME = re.compile(r"[a-z][a-z0-9_-]{1,63}\Z")
SOURCE_DENYLIST = frozenset((
    "the_odds_api_v4", "the-odds-api", "odds-api", "bookmaker",
))
SOURCE_FIELDS = frozenset((
    "id", "sport_key", "home_team", "away_team", "commence_time",
    "last_update", "status",
))
ALLOWED_STATUS = frozenset(("SCHEDULED", "TIMED"))


class CrosswalkError(ValueError):
    """Safe, fixed reason code. Never expose source names, raw IDs or teams."""


def _fail(code):
    raise CrosswalkError(code)


def _instant_safe(value):
    if type(value) is not str or not 1 <= len(value) <= 80:
        _fail("INVALID_SCHEDULE_TIME")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            _fail("INVALID_SCHEDULE_TIME")
        return _instant(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise CrosswalkError("INVALID_SCHEDULE_TIME") from exc


def _capture(value):
    try:
        return _instant(_utc(value))
    except (ReceiptError, ValueError, TypeError, OverflowError) as exc:
        raise CrosswalkError("INVALID_SCHEDULE_CAPTURE_CLOCK") from exc


def _team(value):
    if not _exact_id(value) or len(value) > 100:
        _fail("INVALID_SCHEDULE_IDENTITY")
    # Conservative: normalize case/space and compatibility glyphs, NOT aliases.
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _parse(raw):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_SOURCE_BYTES:
        _fail("INVALID_SCHEDULE_SNAPSHOT_SIZE")
    try:
        rows = json.loads(raw, object_pairs_hook=_pairs_unique,
                          parse_constant=_nonfinite)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise CrosswalkError("INVALID_SCHEDULE_JSON") from exc
    if type(rows) is not list or not 1 <= len(rows) <= MAX_SOURCE_EVENTS:
        _fail("INVALID_SCHEDULE_ROWS")
    for row in rows:
        if type(row) is not dict or set(row) != SOURCE_FIELDS:
            _fail("INVALID_SCHEDULE_EVENT_SCHEMA")
    return rows


def _source(source, *, fixture, kickoff, predicted):
    if (type(source) is not dict or set(source) != {
            "provider_namespace", "snapshot_bytes", "captured_utc",
            "source_event_id"}):
        _fail("INVALID_SOURCE_DESCRIPTOR")
    namespace, selected_id = source["provider_namespace"], source["source_event_id"]
    if (type(namespace) is not str or not SOURCE_NAME.fullmatch(namespace)
            or namespace in SOURCE_DENYLIST
            or not _exact_id(selected_id)):
        _fail("INVALID_SOURCE_IDENTITY")
    captured = _capture(source["captured_utc"])
    if not (predicted - MAX_CAPTURE_AGE <= captured <= predicted
            and captured < kickoff - MAX_TIME_EARLY):
        _fail("STALE_OR_POST_PREDICTION_SCHEDULE")
    snapshot = source["snapshot_bytes"]
    records = _parse(snapshot)
    by_id = [r for r in records if r["id"] == selected_id]
    if len(by_id) != 1:
        _fail("MISSING_OR_DUPLICATED_SCHEDULE_EVENT_ID")
    event = by_id[0]
    if not all(_exact_id(event[k]) for k in ("id", "sport_key")):
        _fail("INVALID_SCHEDULE_IDENTITY")
    home, away = _team(event["home_team"]), _team(event["away_team"])
    expected_home, expected_away = _team(fixture["home_team"]), _team(fixture["away_team"])
    if (home == away or expected_home == expected_away
            or home != expected_home or away != expected_away
            or event["sport_key"] != fixture["sport_key"]):
        _fail("SCHEDULE_FIXTURE_IDENTITY_CONFLICT")
    begin = _instant_safe(event["commence_time"])
    if begin != kickoff:
        _fail("CONFLICTING_KICKOFF_INSTANT")
    if type(event["status"]) is not str or event["status"] not in ALLOWED_STATUS:
        _fail("UNCONFIRMED_SCHEDULE_STATUS")
    updated = _instant_safe(event["last_update"])
    if not updated <= captured:
        _fail("SCHEDULE_UPDATE_AFTER_CAPTURE")
    # Duplicated fixture under a second event ID would make this crosswalk
    # ambiguous even though the selected source ID is unique.
    for row in records:
        if row is event:
            continue
        try:
            if (row["sport_key"] == fixture["sport_key"]
                    and _team(row["home_team"]) == home
                    and _team(row["away_team"]) == away
                    and _instant_safe(row["commence_time"]) == kickoff):
                _fail("AMBIGUOUS_SAME_FIXTURE_IN_SNAPSHOT")
        except CrosswalkError as exc:
            if str(exc) == "AMBIGUOUS_SAME_FIXTURE_IN_SNAPSHOT":
                raise
            # Bad unrelated events cannot be used as positive evidence.
            continue
    # Also reject copied schedules disguised with different JSON whitespace.
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return namespace, hashlib.sha256(snapshot).hexdigest(), hashlib.sha256(canonical).hexdigest()


def crosscheck(raw_odds, receipt, fixture, market, forecast_raw, seal, sources):
    """Replay frozen forecast, then corroborate exactly one 2-source kickoff."""
    try:
        replay = verify_freeze(raw_odds, receipt, fixture, market, forecast_raw, seal)
    except (FreezeError, ReceiptError, ValueError, TypeError, OverflowError) as exc:
        raise CrosswalkError("UNVERIFIED_PRIVATE_PREDICTION_SEAL") from exc
    if replay.get("local_bytes_and_semantics_replayed") is not True:
        _fail("UNVERIFIED_PRIVATE_PREDICTION_SEAL")
    if type(sources) not in (tuple, list) or len(sources) != EXPECTED_SOURCES:
        _fail("TWO_SCHEDULE_SOURCES_REQUIRED")
    kickoff = _instant_safe(fixture["kickoff_utc"])
    predicted = _instant_safe(seal["prediction_utc_claimed"])
    seen = []
    for source in sources:
        seen.append(_source(source, fixture=fixture, kickoff=kickoff, predicted=predicted))
    if seen[0][0] == seen[1][0]:
        _fail("DUPLICATED_SCHEDULE_PUBLISHER_NAMESPACE")
    if seen[0][1] == seen[1][1] or seen[0][2] == seen[1][2]:
        # A whitespace-only edit does not turn one publisher into two.
        _fail("IDENTICAL_SCHEDULE_SNAPSHOTS")
    # This report may later be private-archived. Do NOT export IDs, publisher
    # names, team names, data payload, commercial odds or raw scorelines.
    return {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY",
        "private_forecast_seal_replayed": True,
        "two_distinct_claimed_publisher_namespaces": True,
        "two_nonidentical_local_schedule_snapshots": True,
        "both_schedule_event_ids_unique_in_their_snapshots": True,
        "home_and_away_orientation_exactly_matched": True,
        "kickoff_instant_exactly_agreed": True,
        "both_observations_claimed_available_before_prediction": True,
        "source_raw_payloads_independently_authenticated": False,
        "publisher_independence_independently_verified": False,
        "schedule_captured_clocks_independently_attested": False,
        "source_fixture_id_crosswalk_independently_authenticated": False,
        "actual_kickoff_independently_confirmed": False,
        "certified_independent_forward_samples": 0,
        "eligible_for_model_scoring": False,
        "eligible_for_betting_promotion": False,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("raw-odds", "receipt", "fixture", "market", "forecast", "seal",
                 "source-a", "source-b", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for flag in ("source-a-name", "source-b-name", "source-a-id", "source-b-id",
                 "source-a-captured-utc", "source-b-captured-utc"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args(argv)
    try:
        receipt = _payload_receipt(_read_raw_file(args.receipt))
        fixture = _json_bytes_object(_read_raw_file(args.fixture))
        market = _json_bytes_object(_read_raw_file(args.market))
        seal = _json_bytes_object(_read_raw_file(args.seal))
        sources = [
            {"provider_namespace": args.source_a_name,
             "snapshot_bytes": _read_raw_file(args.source_a),
             "captured_utc": args.source_a_captured_utc,
             "source_event_id": args.source_a_id},
            {"provider_namespace": args.source_b_name,
             "snapshot_bytes": _read_raw_file(args.source_b),
             "captured_utc": args.source_b_captured_utc,
             "source_event_id": args.source_b_id},
        ]
        report = crosscheck(_read_raw_file(args.raw_odds), receipt, fixture,
                            market, _read_raw_file(args.forecast), seal, sources)
        _write_private_new(args.output, report)
    except (CrosswalkError, ReceiptError, FreezeError, ValueError, TypeError,
            OSError, OverflowError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)
                          if isinstance(exc, CrosswalkError) else "INVALID_PRIVATE_INPUT",
                          "production_recommendations": "DISABLED"}))
        return 1
    print(json.dumps({"status": "RESEARCH_ONLY",
                      "independently_confirmed_real_kickoff": False,
                      "certified_independent_forward_samples": 0,
                      "production_recommendations": "DISABLED"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
