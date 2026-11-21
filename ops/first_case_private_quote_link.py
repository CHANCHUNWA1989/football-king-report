"""Private same-response h2h quote → original forecast manifest linkage.

No network or inference. Replays SHA-pinned The Odds API raw capture pack
and requires exact provider-native event ID / team strings / kickoff. The
selected 3-way market must be unique and fully present. Source proof remains
self-attested (not a trusted bookmaker or independently sealed model).
Raw prices are NEVER logged or published and production stays DISABLED.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from ops import private_response_capture as capture
from ops.odds_market import SPORTS
from first_case_payload_binding import (
    FORECAST_KEYS, FORECAST_SCHEMA, QUOTE_SCHEMA, _read_json, _time, _name,
)
from first_case_live_manifest import build as build_manifest

SCHEMA = "football-king-private-first-case-h2h-link-v1"
PROVIDER = "the_odds_api_v4"
MAX_BOOK_ID = 32


def _fail(reason):
    raise ValueError(reason)


def _utc(value):
    return _time(value).isoformat().replace("+00:00", "Z")


def build(forecast_raw, records, *, pack_sha256, bookmaker_id, selection, now=None):
    """Build quote.json and manifest.json bytes from one replayed original pack."""
    f = _read_json(forecast_raw, FORECAST_KEYS, FORECAST_SCHEMA)
    when = datetime.now(timezone.utc) if now is None else now
    if (type(when) is not datetime or when.tzinfo is None
            or when.utcoffset() is None):
        _fail("INVALID_CAPTURE_CLOCK")
    when = when.astimezone(timezone.utc)
    if (type(pack_sha256) is not str or len(pack_sha256) != 64
            or any(c not in "0123456789abcdef" for c in pack_sha256)):
        _fail("INVALID_CAPTURE_PACK_PIN")
    if (type(bookmaker_id) is not str or not 1 <= len(bookmaker_id) <= MAX_BOOK_ID
            or not bookmaker_id.isascii() or
            any(not (c.isalnum() or c in "-_") for c in bookmaker_id)):
        _fail("INVALID_BOOKMAKER_SELECTION")
    if selection not in ("HOME", "DRAW", "AWAY"):
        _fail("UNSUPPORTED_H2H_SELECTION")
    if type(records) is not list or not 1 <= len(records) <= capture.MAX_CAPTURES:
        _fail("INVALID_CAPTURE_RECORD_COUNT")
    fixture_id = _name(f["fixture_id"])
    league = _name(f["league"])
    sport = SPORTS.get(league)
    if sport is None:
        _fail("UNSUPPORTED_LEAGUE_OR_SOURCE")
    home, away = _name(f["home_key"]), _name(f["away_key"])
    kickoff = _time(f["kickoff_utc"])
    if home == away:
        _fail("INVALID_HOME_AWAY_IDENTITY")
    matches = []
    for record in records:
        if type(record) is not dict or set(record) != {"receipt", "raw"}:
            _fail("INVALID_RAW_CAPTURE_RECORD")
        receipt = record["receipt"]
        # Only pack replay can authenticate structural request constraints;
        # do not accept arbitrary caller-supplied quote lists here.
        if type(receipt) is not dict or type(record["raw"]) is not bytes:
            _fail("INVALID_RAW_CAPTURE_RECORD")
        if receipt.get("endpoint_path") == "/sports/":
            continue
        endpoint = receipt.get("endpoint_path")
        expected = f"/sports/{sport}/odds/"
        if type(endpoint) is not str or not endpoint.startswith("/sports/"):
            _fail("INVALID_CAPTURE_ENDPOINT")
        # Parse every odds response to detect duplicate native event IDs in
        # two different captures. No first-response or newest-response wins.
        events = capture._body(record["raw"])
        if len(events) > 500:
            _fail("OVERSIZED_PROVIDER_EVENT_SCOPE")
        for event in events:
            if type(event) is dict and event.get("id") == fixture_id:
                matches.append((event, receipt, endpoint))
    if len(matches) != 1:
        _fail("NATIVE_EVENT_MISSING_OR_DUPLICATE_ACROSS_PACK")
    event, receipt, endpoint = matches[0]
    if endpoint != f"/sports/{sport}/odds/":
        _fail("WRONG_PROVIDER_SPORT_SCOPE")
    if (event.get("sport_key") != sport or event.get("home_team") != home
            or event.get("away_team") != away
            or _time(event.get("commence_time")) != kickoff
            or event.get("completed") is True
            or event.get("is_outright") is True):
        _fail("NATIVE_EVENT_TEAM_KICKOFF_OR_PHASE_MISMATCH")
    books = event.get("bookmakers")
    if type(books) is not list or len(books) > 100:
        _fail("INVALID_BOOKMAKER_SCOPE")
    target = [book for book in books if type(book) is dict
              and book.get("key") == bookmaker_id]
    if len(target) != 1:
        _fail("BOOKMAKER_MISSING_OR_DUPLICATE")
    markets = target[0].get("markets")
    if type(markets) is not list or len(markets) > 20:
        _fail("INVALID_MARKET_SCOPE")
    h2h = [m for m in markets if type(m) is dict and m.get("key") == "h2h"]
    if len(h2h) != 1:
        _fail("H2H_MARKET_MISSING_OR_DUPLICATE")
    market = h2h[0]
    if (market.get("period") not in (None, "full", "full_game", "ft")
            or market.get("suspended_at") is not None):
        _fail("INVALID_MARKET_PHASE")
    outcomes = market.get("outcomes")
    if (type(outcomes) is not list or len(outcomes) != 3
            or Counter(x.get("name") for x in outcomes if type(x) is dict)
            != Counter([home, "Draw", away])):
        _fail("INCOMPLETE_OR_DUPLICATE_H2H_SIDES")
    for row in outcomes:
        if type(row) is not dict or row.get("point") is not None:
            _fail("INVALID_H2H_LINE")
        value = row.get("price")
        if (type(value) not in (int, float)
                or not (1.01 <= value <= 100)):
            _fail("INVALID_H2H_PRICE")
    name = {"HOME": home, "DRAW": "Draw", "AWAY": away}[selection]
    prices = [x["price"] for x in outcomes if x["name"] == name]
    if len(prices) != 1:
        _fail("INVALID_H2H_SIDE")
    captured = _time(receipt["completed_utc"])
    observed = _time(market.get("last_update"))
    requested = _time(receipt["requested_utc"])
    if not (requested <= captured <= when and observed <= captured
            and observed <= _time(f["captured_utc"])
            and captured <= _time(f["captured_utc"])):
        _fail("CAPTURE_OR_MARKET_CLOCK_CONFLICT")
    # Quote carries the *entire exact private pack SHA*, rather than relying
    # on an unrelated user-selected bookmaker label or normalized aggregate.
    # This digest still does not prove actual vendor origin or trust.
    provider = f"{PROVIDER}/{bookmaker_id}/{pack_sha256}"
    if len(provider) > 120:
        _fail("PROVIDER_PROVENANCE_FIELD_TOO_LONG")
    quote = {
        "schema": QUOTE_SCHEMA,
        "fixture_id": fixture_id,
        "league": league,
        "home_key": home,
        "away_key": away,
        "kickoff_utc": _utc(f["kickoff_utc"]),
        "provider": provider,
        "provider_event_id": fixture_id,
        "market": "h2h",
        "selection": selection,
        "line": None,
        "observed_utc": _utc(market["last_update"]),
        "captured_utc": _utc(receipt["completed_utc"]),
        "decimal_odds": prices[0],
        "production_recommendations": "DISABLED",
    }
    quote_raw = (json.dumps(quote, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":"), allow_nan=False)+"\n").encode()
    try:
        manifest_raw, report = build_manifest(forecast_raw, quote_raw, now=when)
    except (ValueError, TypeError, OverflowError):
        raise ValueError("LIVE_QUOTE_OR_FORECAST_NOT_SEALABLE") from None
    return quote_raw, manifest_raw, {
        "schema": SCHEMA,
        "status": "HOLD",
        "reason": "PINNED_PRIVATE_PACK_REPLAYED_MODEL_AND_EXECUTABILITY_UNVERIFIED",
        "private_pack_sha256": pack_sha256,
        "quote_sha256": hashlib.sha256(quote_raw).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "original_capture_pin_replayed": False,
        "exact_native_id_team_kickoff_matched": True,
        "market_h2h_threeway_present": True,
        "source_native_id_independently_authenticated": False,
        "forecast_origin_independently_authenticated": False,
        "source_capture_time_independently_authenticated": False,
        "independent_tsa_timestamp_verified": False,
        "bookmaker_quote_executable_authenticated": False,
        "certified_forward_case_count": 0,
        "positive_ev_verified": False,
        "eligible_for_model_scoring": False,
        "production_recommendations": "DISABLED",
    }


def _write_new(target, raw):
    """Persist no selected price to stdout; mode 0600; reject overwrites."""
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        Path(target).unlink(missing_ok=True)
        raise


def create(private_dir, forecast_path, *, source_sha, run_id, attempt,
           expected_manifest_sha256, bookmaker_id, selection,
           quote_output, manifest_output, now=None):
    """Private operator: source SHA pin + strict event join + create-only outputs."""
    fpath, qpath, mpath = Path(forecast_path), Path(quote_output), Path(manifest_output)
    # Never place private bookmaker/source data inside a repository worktree.
    if (qpath == mpath or qpath in (fpath, Path(private_dir))
            or mpath in (fpath, Path(private_dir))
            or any(p.exists() or p.is_symlink() for p in (qpath, mpath))
            or any(not p.parent.is_dir() or p.parent.is_symlink() for p in (qpath, mpath))):
        _fail("OUTPUT_EXISTS_OR_UNSAFE")
    # The market originals and derived quote must never live in the public
    # repository. Reuse the existing private-pack permission and ancestry
    # checks: no symlinks, no Git worktree ancestors and mode 0700 parents.
    if qpath.parent != mpath.parent or fpath.parent != qpath.parent:
        _fail("PRIVATE_OUTPUTS_MUST_SHARE_DIRECTORY_WITH_FORECAST")
    descriptor = capture._open_chain(capture._path(qpath.parent))
    try:
        capture._directory_mode(descriptor)
        raw_f = capture._read(descriptor, fpath.name, 1_000_000)
    finally:
        os.close(descriptor)
    records = capture.replay_records(
        private_dir, source_sha=source_sha, run_id=run_id, attempt=attempt,
        expected_manifest_sha256=expected_manifest_sha256)
    raw_quote, raw_manifest, report = build(
        raw_f, records, pack_sha256=expected_manifest_sha256,
        bookmaker_id=bookmaker_id, selection=selection, now=now)
    descriptor = capture._open_chain(capture._path(qpath.parent))
    try:
        if capture._read(descriptor, fpath.name, 1_000_000) != raw_f:
            _fail("FORECAST_CHANGED_DURING_SOURCE_REPLAY")
    finally:
        os.close(descriptor)
    created_quote = False
    try:
        _write_new(qpath, raw_quote)
        created_quote = True
        _write_new(mpath, raw_manifest)
    except BaseException:
        # Never delete a bystander path created by a racing process after
        # O_EXCL rejected its attempt to create a manifest.
        if created_quote:
            qpath.unlink(missing_ok=True)
        raise
    return {**report, "original_capture_pin_replayed": True}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("private-dir", "forecast", "source-sha", "run-id",
                 "attempt", "expected-manifest-sha256", "bookmaker-id",
                 "selection", "quote-output", "manifest-output"):
        p.add_argument("--"+name, required=True)
    a = p.parse_args(argv)
    try:
        report = create(
            a.private_dir, a.forecast, source_sha=a.source_sha,
            run_id=a.run_id, attempt=a.attempt,
            expected_manifest_sha256=a.expected_manifest_sha256,
            bookmaker_id=a.bookmaker_id, selection=a.selection,
            quote_output=a.quote_output, manifest_output=a.manifest_output)
    except (ValueError, TypeError, OSError, OverflowError, RecursionError) as exc:
        # Never emit raw quotes, paths, provider payloads or secrets.
        reason = (str(exc) if isinstance(exc, ValueError) and
                  not isinstance(exc, capture.CaptureError) else
                  "PRIVATE_ORIGINAL_REPLAY_REJECTED")
        report = {
            "schema": SCHEMA, "status": "HOLD", "reason": reason,
            "certified_forward_case_count": 0,
            "positive_ev_verified": False,
            "production_recommendations": "DISABLED",
        }
    print(json.dumps(report, sort_keys=True))
    if not report.get("original_capture_pin_replayed"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
