"""Offline atomic-quote coverage gate for UCL corners and first-half totals.

Only the two special markets are in scope. Existing general-market quote gates
handle H2H/spreads/full-time goals. No API requests or bookmaker execution.
No input price, bookmaker name, provider ID or token is echoed in public output.
"""
from collections import Counter
from datetime import datetime, timezone
from math import isfinite

from ucl_four_market_shadow import CASES, KICKOFF_UTC

SCHEMA = "football-king-ucl-special-market-atomic-gate-v1"
SPECIAL = {
    case_id: (home, away, market, selection, line)
    for case_id, home, away, market, selection, line in CASES
    if market in ("corners_total", "first_half_goals")
}
MAX_ROWS = 100
QUOTE_MAX_AGE_SECONDS = 120
MIN_BEFORE_KICKOFF_SECONDS = 600

_ROW_KEYS = frozenset((
    "case_id", "fixture", "provider", "provider_event_id",
    "bookmaker_id", "market_id", "market_updated_utc",
    "captured_utc", "outcomes"
))
_FIXTURE_KEYS = frozenset(("home", "away", "kickoff_utc"))
_OUTCOME_KEYS = frozenset(("selection", "line", "decimal_odds"))


def _clock(raw):
    if not isinstance(raw, (str, datetime)):
        raise ValueError("INVALID_TIME")
    try:
        dt = raw if isinstance(raw, datetime) else datetime.fromisoformat(
            raw.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("NAIVE_TIME")
        return dt.astimezone(timezone.utc)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError("INVALID_TIME") from exc


def _identity(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 128 and not any(
        ord(char) < 32 for char in value
    )


def _finite_real(value):
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except (OverflowError, ValueError):
        return False


def _quote_price(value):
    return _finite_real(value) and 1.01 <= value <= 100.0


def _canonical_key(row):
    """A duplicate must poison *all* copies, even malformed duplicates."""
    if not isinstance(row, dict):
        return None
    case_id, book_id = row.get("case_id"), row.get("bookmaker_id")
    if not isinstance(case_id, str) or case_id not in SPECIAL or not _identity(book_id):
        return None
    return case_id, book_id


def _reason(row, now, duplicate_keys, ambiguous_native_ids):
    if not isinstance(row, dict) or set(row) != _ROW_KEYS:
        return "INVALID_ROW_SHAPE"
    case_id = row["case_id"]
    if not isinstance(case_id, str) or case_id not in SPECIAL:
        return "UNSUPPORTED_CASE"
    if _canonical_key(row) in duplicate_keys:
        return "DUPLICATE_BOOKMAKER_CASE"
    if not all(_identity(row.get(k)) for k in
               ("provider", "provider_event_id", "bookmaker_id")):
        return "INVALID_ORIGIN_CLAIM"
    # Native IDs are only unique within a single provider namespace.
    # The same spelling across two unrelated providers is not a collision.
    if (row["provider"], row["provider_event_id"]) in ambiguous_native_ids:
        return "AMBIGUOUS_NATIVE_EVENT_ID"
    home, away, market, side, requested = SPECIAL[case_id]
    fixture = row["fixture"]
    if (not isinstance(fixture, dict) or set(fixture) != _FIXTURE_KEYS
            or fixture["home"] != home or fixture["away"] != away
            or fixture["kickoff_utc"] != KICKOFF_UTC):
        return "FIXTURE_IDENTITY_OR_KICKOFF_MISMATCH"
    if row["market_id"] != market:
        return "WRONG_MARKET_PERIOD_OR_CATEGORY"
    try:
        captured = _clock(row["captured_utc"])
        updated = _clock(row["market_updated_utc"])
        kickoff = _clock(fixture["kickoff_utc"])
    except ValueError:
        return "INVALID_TIME"
    if not updated <= captured <= now < kickoff:
        return "INVALID_CHRONOLOGY"
    if (kickoff - now).total_seconds() <= MIN_BEFORE_KICKOFF_SECONDS:
        return "TOO_CLOSE_TO_KICKOFF"
    if (now - captured).total_seconds() > QUOTE_MAX_AGE_SECONDS:
        return "STALE_CAPTURE"
    if (now - updated).total_seconds() > QUOTE_MAX_AGE_SECONDS:
        return "STALE_MARKET_UPDATE"

    outcomes = row["outcomes"]
    # Exactly two sides as one market block from ONE source and bookmaker.
    # Do not repair missing/duplicated sides by stitching across other rows.
    if not isinstance(outcomes, list) or len(outcomes) != 2:
        return "INCOMPLETE_ATOMIC_PAIR"
    seen = set()
    for outcome in outcomes:
        if not isinstance(outcome, dict) or set(outcome) != _OUTCOME_KEYS:
            return "INVALID_OUTCOME"
        selection = outcome["selection"]
        if selection not in ("OVER", "UNDER") or selection in seen:
            return "INCOMPLETE_OR_DUPLICATE_SIDE"
        seen.add(selection)
        point = outcome["line"]
        if (not _finite_real(point) or point != requested):
            return "MISMATCHED_REQUESTED_LINE"
        if not _quote_price(outcome["decimal_odds"]):
            return "INVALID_DECIMAL_ODDS"
    if seen != {"OVER", "UNDER"}:
        return "INCOMPLETE_OR_DUPLICATE_SIDE"
    return None


def audit(rows=None, *, now_utc=None):
    """Check supplied untrusted blocks; *never* authenticate bookmaker origin.

    Every accepted block is only structurally complete, and can never produce
    verified EV, probabilities, actual-offer claims or betting permission.
    """
    now = _clock(datetime.now(timezone.utc) if now_utc is None else now_utc)
    invalid_batch = not isinstance(rows, list) or len(rows) > MAX_ROWS
    if rows is None:
        rows = []
        invalid_batch = False
    safe_rows = [] if invalid_batch else rows

    counts = Counter(key for row in safe_rows
                     if (key := _canonical_key(row)) is not None)
    duplicate_keys = {key for key, count in counts.items() if count > 1}

    native_cases = {}
    for row in safe_rows:
        if (isinstance(row, dict) and isinstance(row.get("case_id"), str)
                and row["case_id"] in SPECIAL):
            native_id = row.get("provider_event_id")
            provider = row.get("provider")
            if _identity(native_id) and _identity(provider):
                native_cases.setdefault((provider, native_id), set()).add(
                    row["case_id"])
    ambiguous_native_ids = {
        scoped_id for scoped_id, case_ids in native_cases.items()
        if len(case_ids) > 1
    }

    summaries = {case_id: {
        "case_id": case_id, "market": market, "selection": side,
        "requested_line_not_an_observed_offer": line,
        "submitted_blocks": 0, "atomic_pairs_structurally_valid": 0,
        "state": "HOLD_NO_VALID_ATOMIC_PAIR",
        "independent_source_authenticated": False,
        "executable_bookmaker_quote_verified": False,
        "positive_expected_value_verified": False,
    } for case_id, (_, _, market, side, line) in SPECIAL.items()}
    rejects = Counter()
    if invalid_batch:
        rejects["INVALID_OR_OVERSIZE_BATCH"] += 1

    for row in safe_rows:
        if isinstance(row, dict) and isinstance(row.get("case_id"), str):
            case = summaries.get(row["case_id"])
            if case is not None:
                case["submitted_blocks"] += 1
        else:
            case = None
        reason = _reason(row, now, duplicate_keys, ambiguous_native_ids)
        if reason is not None:
            rejects[reason] += 1
            continue
        case["atomic_pairs_structurally_valid"] += 1

    for case in summaries.values():
        if case["atomic_pairs_structurally_valid"]:
            case["state"] = "RESEARCH_ONLY_ATOMIC_PAIR_UNAUTHENTICATED"

    return {
        "schema": SCHEMA, "checked_utc": now.isoformat(),
        "status": "HOLD", "research_only": True,
        "supported_market_types": ["corners_total", "first_half_goals"],
        "cases": list(summaries.values()),
        "submitted_blocks": len(safe_rows),
        "structurally_valid_pairs": sum(
            case["atomic_pairs_structurally_valid"]
            for case in summaries.values()),
        "rejection_counts": dict(sorted(rejects.items())),
        "actual_quote_execution_authenticated": False,
        "validated_corner_or_first_half_model": False,
        "market_bookmaker_provenance_independently_verified": False,
        "bets_authorized": 0,
        "production_recommendations": "DISABLED",
    }
