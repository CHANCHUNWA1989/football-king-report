"""Bind a private, replayed raw odds snapshot to ONE exact caller fixture/line.

Offline/read-only. This is a structural integrity audit, not a trusted
cross-provider fixture crosswalk, immutable external attestation, quote
executability proof, or production betting recommendation.

Do not export raw bookmaker IDs, raw odds, or the caller's private fixture IDs.
"""
from collections import Counter, defaultdict
from datetime import datetime
from math import isfinite

from live_market_research import utc
from market_quote_gate import extract
from private_quote_snapshot_receipt import (
    ReceiptError, _payload, verify_receipt,
)

SCHEMA = "football-king-private-fixture-quote-binding-v1"
REQUIRED_FIXTURE = frozenset((
    "provider_event_id", "sport_key", "home_team", "away_team", "kickoff_utc",
))
REQUIRED_MARKET = {
    "h2h": frozenset(("market_type",)),
    "spreads": frozenset(("market_type", "home_line")),
    "totals": frozenset(("market_type", "goals_line")),
}
MAX_ID_LENGTH = 128


class BindingError(ValueError):
    """Constant non-sensitive error codes only."""


def _fail(code):
    raise BindingError(code)


def _exact_id(value):
    return type(value) is str and 1 <= len(value) <= MAX_ID_LENGTH and value == value.strip()


def _instant(value):
    try:
        if type(value) is not str or not value.strip():
            _fail("INVALID_FIXTURE_KICKOFF")
        stamp = utc(value)
        if not isinstance(stamp, datetime) or stamp.utcoffset() is None:
            _fail("INVALID_FIXTURE_KICKOFF")
        return stamp
    except (TypeError, ValueError, OverflowError) as exc:
        raise BindingError("INVALID_FIXTURE_KICKOFF") from exc


def _quarter_units(value, kind):
    if type(value) not in (float, int) or not isfinite(value):
        _fail("INVALID_QUARTER_LINE")
    if (kind == "totals" and not 0 <= value <= 20
            or kind == "spreads" and not -15 <= value <= 15):
        _fail("INVALID_QUARTER_LINE")
    units = value * 4
    if not isfinite(units) or units != int(units):
        _fail("INVALID_QUARTER_LINE")
    return int(units)


def _validate_inputs(fixture, market):
    if type(fixture) is not dict or set(fixture) != REQUIRED_FIXTURE:
        _fail("INVALID_FIXTURE_BINDING")
    if not all(_exact_id(fixture[key]) for key in (
            "provider_event_id", "sport_key", "home_team", "away_team")):
        _fail("INVALID_FIXTURE_BINDING")
    if fixture["home_team"].casefold() == fixture["away_team"].casefold():
        _fail("INVALID_FIXTURE_BINDING")
    kickoff = _instant(fixture["kickoff_utc"])
    if (type(market) is not dict or type(market.get("market_type")) is not str
            or market["market_type"] not in REQUIRED_MARKET):
        _fail("INVALID_MARKET_BINDING")
    kind = market["market_type"]
    if set(market) != REQUIRED_MARKET[kind]:
        _fail("INVALID_MARKET_BINDING")
    units = None if kind == "h2h" else _quarter_units(
        market["home_line"] if kind == "spreads" else market["goals_line"], kind)
    return kickoff, kind, units


def bind_private_fixture(raw, receipt, fixture, market):
    """Match source-native event identity, exact kickoff, and atomic quote sides.

    The input fixture and receipt are both supplied by the caller. A successful
    result is not independent authentication of either one's external origin.
    """
    kickoff, market_type, requested_line = _validate_inputs(fixture, market)
    try:
        replay = verify_receipt(raw, receipt)
        if replay.get("bytes_and_semantics_replayed") is not True:
            _fail("RECEIPT_NOT_REPLAYED")
        payload = _payload(raw)
    except ReceiptError as exc:
        raise BindingError("PRIVATE_RECEIPT_REPLAY_FAILED") from exc

    native_id = fixture["provider_event_id"]
    id_counts = Counter(
        row.get("id") for row in payload
        if type(row) is dict and type(row.get("id")) is str)
    if id_counts[native_id] != 1:
        _fail("MISSING_OR_AMBIGUOUS_NATIVE_EVENT_ID")
    event = next(row for row in payload if type(row) is dict and row.get("id") == native_id)
    if (event.get("sport_key") != fixture["sport_key"]
            or event.get("home_team") != fixture["home_team"]
            or event.get("away_team") != fixture["away_team"]):
        _fail("FIXTURE_IDENTITY_MISMATCH")
    if _instant(event.get("commence_time")) != kickoff:
        _fail("FIXTURE_KICKOFF_MISMATCH")

    stamp = receipt["captured_utc_claimed_by_caller"]
    try:
        report = extract([event], captured_utc=stamp, league=fixture["sport_key"],
                         home=fixture["home_team"], away=fixture["away_team"])
    except (ValueError, KeyError, TypeError, OverflowError) as exc:
        raise BindingError("PRIVATE_QUOTE_EXTRACTION_FAILED") from exc
    claimed_capture = _instant(stamp)
    # Prevent market_quote_gate's tolerated vendor future-skew from becoming
    # apparent exact pre-match line evidence.
    groups = defaultdict(list)
    for quote in report["quotes"]:
        if (quote.get("quote_pre_match_at_capture") is not True
                or quote.get("source") != "the_odds_api_v4"
                or quote.get("market") != market_type
                or quote.get("event_id") != native_id):
            continue
        try:
            updated = _instant(quote["market_last_update_utc"])
            if updated > claimed_capture or _instant(quote["kickoff_utc"]) != kickoff:
                continue
            if market_type == "h2h":
                normalized_units = None
            elif market_type == "totals":
                normalized_units = _quarter_units(quote["point"], "totals")
            else:
                points = _quarter_units(quote["point"], "spreads")
                normalized_units = points if quote["outcome"] == fixture["home_team"] else -points
            if normalized_units != requested_line:
                continue
            key = (quote["bookmaker"], quote["market"],
                   normalized_units, quote["market_last_update_utc"])
            groups[key].append(quote)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

    required = (
        {fixture["home_team"], fixture["away_team"], "Draw"}
        if market_type == "h2h"
        else {fixture["home_team"], fixture["away_team"]}
        if market_type == "spreads"
        else {"Over", "Under"}
    )
    complete = 0
    for rows in groups.values():
        if len(rows) != len(required) or {q["outcome"] for q in rows} != required:
            continue
        if market_type == "spreads":
            points = {q["outcome"]: _quarter_units(q["point"], "spreads") for q in rows}
            if points[fixture["home_team"]] != -points[fixture["away_team"]]:
                continue
        if market_type == "totals":
            points = {q["outcome"]: _quarter_units(q["point"], "totals") for q in rows}
            if points["Over"] != points["Under"]:
                continue
        complete += 1

    return {
        "schema": SCHEMA,
        "status": "RESEARCH_ONLY" if complete else "HOLD",
        "raw_snapshot_digest_replayed": True,
        "caller_fixture_matched_exact_native_id_and_kickoff": True,
        "market_type_requested": market_type,
        "atomic_bookmaker_groups_for_requested_line": complete,
        "requested_line_structurally_observed": complete > 0,
        "cross_provider_fixture_id_authenticated": False,
        "fixture_assertion_independently_authenticated": False,
        "quote_source_independently_authenticated": False,
        "quote_capture_clock_independently_authenticated": False,
        "executable_bookmaker_quote_verified": False,
        "independent_model_ev_verified": False,
        "eligible_for_betting_promotion": False,
        "production_recommendations": "DISABLED",
    }
