"""Quota-free, read-only preflight for an existing J1 prematch coverage snapshot.

Deliberately no network, API key, paid requests, bookmaker raw prices or picks.
Do not treat sanitized *coverage* counts as point-in-time model inputs or
tradable prices. Reuses the existing publisher guard and exact J1 quota cap.
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from japan_free_market import MIN_THE_ODDS_LEFT, SPORT, utc
from japan_free_market_guard import check as check_public_metadata

SCHEMA = "football-king-j1-shadow-zero-credit-preflight-v1"
MAX_DIAGNOSTIC_AGE = timedelta(hours=2)
PROVIDER_ORDER = ("propline", "therundown", "the_odds_api_j1")


def _base():
    return {
        "schema": SCHEMA, "sport_key": SPORT, "market_scope": "PREMATCH_H2H_1X2",
        "status": "HOLD", "decision": "HOLD",
        "production_recommendations": "DISABLED",
        "requests_performed": 0, "api_credits_spent": 0,
        "network_collection_allowed": False, "new_odds_request_allowed": False,
        "has_live_or_executable_quote": False, "same_instant_market_quote_verified": False,
        "two_sources_independently_verified": False, "presealed_fixture_ids_verified": False,
        "raw_market_bytes_available": False, "shadow_model_scoring_eligible": False,
        "positive_ev_verified": False, "certified_forward_samples": 0,
        "research_recommendation": None, "stake": None,
        "cached_metadata_valid": False, "cached_metadata_recent": False,
        "cached_collected_utc": None,
        "cached_prop_line_coverage_events": 0,
        "cached_two_api_fixture_comparisons": 0,
        "cached_odds_api_remaining": None,
        "cached_quota_is_not_current": True,
        "j1_odds_reserve_credits": MIN_THE_ODDS_LEFT,
        "blockers": [],
    }


def assess(doc, *, now=None):
    """Evaluate only a previously published, sanitized local metadata document.

    This cannot unlock API calls. Even if quota appears abundant, that would
    need a fresh provider response, account entitlement, independent evidence,
    source-native IDs, quote bytes and a separately approved execution plan.
    """
    result = _base()
    blockers = []
    if now is None:
        now = datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        return {**result, "blockers": ["INVALID_ASSESSMENT_CLOCK"]}
    now = now.astimezone(timezone.utc)
    try:
        checked_stamp = check_public_metadata(doc, now=now)
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
        return {**result, "blockers": ["INVALID_OR_EXPIRED_PUBLIC_J1_METADATA"]}

    # The publication guard allows a 48h publication window. A much narrower
    # limit is required even to *discuss* last-observed market coverage.
    age = now - checked_stamp
    if age < timedelta(0):
        return {**result, "blockers": ["FUTURE_J1_METADATA"]}
    recent = age <= MAX_DIAGNOSTIC_AGE
    if not recent:
        blockers.append("CACHED_J1_METADATA_TOO_OLD_FOR_SHADOW_DIAGNOSTIC")
    source_rows = doc["j1_free_prematch_sources"]
    by_name = {row["provider"]: row for row in source_rows}
    if set(by_name) != set(PROVIDER_ORDER):
        return {**result, "blockers": ["UNEXPECTED_PROVIDER_SET"]}

    prop = by_name["propline"]
    rundown = by_name["therundown"]
    odds = by_name["the_odds_api_j1"]
    prop_count = (
        prop["fresh_3way_event_count"] if prop["status"] == "RESEARCH_ONLY" else 0
    )
    if prop_count:
        blockers.append("PROPLINE_COUNTS_ONLY_NO_NATIVE_QUOTE_OR_MODEL_SNAPSHOT")
    else:
        blockers.append("NO_PROP_LINE_H2H_COVERAGE_IN_SNAPSHOT")
    if rundown["status"] == "NOT_CONFIGURED":
        blockers.append("THERUNDOWN_NOT_CONFIGURED_IN_SNAPSHOT")
    elif rundown["status"] != "RESEARCH_ONLY":
        blockers.append("THERUNDOWN_NO_FRESH_RESEARCH_COVERAGE")
    cross = doc["cross_feed_consistency_observation"]
    pairs = cross["same_fixture_two_api_observations"]
    if pairs == 0:
        blockers.append("NO_MATCHED_TWO_API_J1_FIXTURE_COMPARISONS")
    else:
        blockers.append("TWO_API_COVERAGE_NOT_INDEPENDENT_BOOKMAKER_VERIFICATION")

    remaining = odds.get("quota_remaining")
    # 220 is the *J1-specific* reserve. A book's remaining quota from
    # historical headers is NOT a new authorization or current account state.
    if type(remaining) is not int:
        blockers.append("ODDS_API_REMAINING_NOT_IN_CACHED_METADATA")
    elif remaining <= MIN_THE_ODDS_LEFT:
        blockers.append("ODDS_API_J1_RESERVE_PROTECTED")
    else:
        blockers.append("CACHED_ODDS_API_QUOTA_CANNOT_AUTHORIZE_NEW_REQUEST")
    if odds["status"] != "RESEARCH_ONLY":
        blockers.append("ODDS_API_J1_MARKET_NOT_AVAILABLE_IN_SNAPSHOT")
    blockers.extend((
        "NO_NATIVE_MATCHED_FIXTURE_AND_MARKET_ORIGINAL_BYTES",
        "J1_FIXTURE_INDEPENDENCE_AND_KICKOFF_NOT_CERTIFIED",
        "NO_EXECUTABLE_PRICE_OR_CALIBRATED_J1_MODEL",
    ))
    return {
        **result,
        "cached_metadata_valid": True,
        "cached_metadata_recent": recent,
        "cached_collected_utc": checked_stamp.isoformat(),
        "cached_prop_line_coverage_events": prop_count,
        "cached_two_api_fixture_comparisons": pairs,
        "cached_odds_api_remaining": remaining if type(remaining) is int else None,
        "cached_quota_is_not_current": True,
        "blockers": sorted(set(blockers)),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-file", type=Path, default=Path("market/japan_free_status.json"))
    args = parser.parse_args(argv)
    try:
        if args.status_file.stat().st_size > 100_000:
            raise ValueError("OVERSIZED_CACHED_J1_METADATA")
        with args.status_file.open(encoding="utf-8") as handle:
            doc = json.load(handle)
        result = assess(doc)
    except (OSError, ValueError, UnicodeError, TypeError):
        result = {**_base(), "blockers": ["MISSING_OR_UNREADABLE_J1_METADATA"]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    # Always fail closed; an offline stale metadata probe is not a launch gate.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
