"""Offline nine-fixture UEFA Champions League coverage and gap audit.

The official fixture manifest is schedule evidence, NOT an API native event ID.
Public market/latest.json holds no guaranteed UCL bookmaker quotes. This module
can only count source-scoped, explicitly bound PUBLIC 1X2 consensus observations.
Every fixture stays HOLD, even when a structurally valid 1X2 row is supplied.
No APIs, credentials, model promotion, betting advice or raw prices.
"""
import argparse
import json
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = "football-king-ucl-nine-fixture-coverage-v1"
MANIFEST_SCHEMA = "football-king-ucl-md4-manifest-v1"
PUBLIC_SCHEMA = "football-king-market-consensus-v1"
UCL_SPORT_KEY = "soccer_uefa_champs_league"
PUBLIC_PROVIDER = "the-odds-api.com/v4"
MAX_CAPTURE_AGE_SECONDS = 7200
MAX_MARKET_UPDATE_AGE_SECONDS = 120
MAX_EVENTS = 500
SOURCE_ROW_FIELDS = frozenset({
    "source_event_id", "league", "home", "away", "kickoff_utc",
    "market_last_update_utc", "contributing_bookmakers",
    "p_home", "p_draw", "p_away", "probabilities_are_no_vig_consensus",
    "prediction_or_value_bet",
})
BINDING_FIELDS = frozenset({
    "local_request_id", "source_event_id", "provider", "provider_sport_key",
})
MANIFEST_FIELDS = frozenset({
    "schema", "competition", "season", "matchday", "match_date_utc",
    "fixture_source_url", "corroborating_schedule_url",
    "official_fixture_ids_available", "local_ids_are_provider_ids",
    "fixtures",
})
FIXTURE_FIELDS = frozenset({
    "local_request_id", "home", "away", "kickoff_utc",
})
REQUIRED_MARKETS = (
    "h2h", "asian_handicap", "full_time_totals", "first_half_goals",
    "corners_total",
)


def _id(value):
    return (isinstance(value, str) and 0 < len(value.strip()) <= 128
            and all(ord(ch) >= 32 for ch in value))


def _utc(value):
    if not isinstance(value, (datetime, str)):
        raise ValueError("INVALID_TIMESTAMP")
    try:
        timestamp = (value if isinstance(value, datetime)
                     else datetime.fromisoformat(value.replace("Z", "+00:00")))
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("NAIVE_TIMESTAMP")
        return timestamp.astimezone(timezone.utc)
    except (OverflowError, ValueError, TypeError) as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc


def validate_manifest(manifest):
    """Reject incomplete/synthetic official scope; IDs are ONLY local labels."""
    if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
        raise ValueError("INVALID_FIXTURE_MANIFEST")
    if (manifest["schema"] != MANIFEST_SCHEMA
            or manifest["competition"] != "UEFA Champions League"
            or manifest["season"] != "2026/27"
            or type(manifest["matchday"]) is not int or manifest["matchday"] != 4
            or manifest["match_date_utc"] != "2026-11-03"
            or manifest["official_fixture_ids_available"] is not False
            or manifest["local_ids_are_provider_ids"] is not False
            or not isinstance(manifest["fixture_source_url"], str)
            or not manifest["fixture_source_url"].startswith(
                "https://www.uefa.com/uefachampionsleague/")
            or not isinstance(manifest["corroborating_schedule_url"], str)
            or not manifest["corroborating_schedule_url"].startswith("https://")):
        raise ValueError("INVALID_FIXTURE_MANIFEST")
    fixtures = manifest["fixtures"]
    if not isinstance(fixtures, list) or len(fixtures) != 9:
        raise ValueError("NOT_EXACT_NINE_FIXTURES")
    ids, pairings, team_ids, kickoffs = set(), set(), set(), Counter()
    for fixture in fixtures:
        if not isinstance(fixture, dict) or set(fixture) != FIXTURE_FIELDS:
            raise ValueError("INVALID_FIXTURE_ENTRY")
        fid, home, away = (fixture.get(key) for key in
                           ("local_request_id", "home", "away"))
        if not all(_id(item) for item in (fid, home, away)):
            raise ValueError("INVALID_FIXTURE_IDENTITY")
        if home.casefold() == away.casefold():
            raise ValueError("SELF_MATCH")
        if fid in ids or (home, away) in pairings:
            raise ValueError("DUPLICATED_FIXTURE")
        ids.add(fid)
        pairings.add((home, away))
        team_ids.update((home, away))
        kickoff = _utc(fixture["kickoff_utc"])
        if kickoff.isoformat() not in (
                "2026-11-03T17:45:00+00:00",
                "2026-11-03T20:00:00+00:00"):
            raise ValueError("UNSUPPORTED_KICKOFF")
        kickoffs[kickoff.isoformat()] += 1
    if (len(team_ids) != 18 or kickoffs["2026-11-03T17:45:00+00:00"] != 2
            or kickoffs["2026-11-03T20:00:00+00:00"] != 7):
        raise ValueError("INCONSISTENT_OFFICIAL_SLATE")
    return fixtures


def _public_row_valid(row, as_of):
    if not isinstance(row, dict) or set(row) != SOURCE_ROW_FIELDS:
        return False
    if not all(_id(row.get(k)) for k in
               ("source_event_id", "league", "home", "away")):
        return False
    if row["home"].casefold() == row["away"].casefold():
        return False
    if (row.get("probabilities_are_no_vig_consensus") is not True
            or row.get("prediction_or_value_bet") is not False
            or type(row.get("contributing_bookmakers")) is not int
            or not 1 <= row["contributing_bookmakers"] <= 100):
        return False
    probs = [row.get(k) for k in ("p_home", "p_draw", "p_away")]
    if any(type(p) not in (int, float) for p in probs):
        return False
    try:
        if (any(not math.isfinite(p) or not 0 < p < 1 for p in probs)
                or abs(sum(probs) - 1) > 1e-5):
            return False
    except (OverflowError, ValueError):
        return False
    try:
        update = _utc(row["market_last_update_utc"])
        kickoff = _utc(row["kickoff_utc"])
    except ValueError:
        return False
    return update <= as_of < kickoff


def _read_public_snapshot(snapshot, now):
    if not isinstance(snapshot, dict):
        return "INVALID_PUBLIC_SNAPSHOT", [], None
    try:
        as_of = _utc(snapshot["as_of_utc"])
    except (ValueError, KeyError):
        return "INVALID_PUBLIC_SNAPSHOT", [], None
    events = snapshot.get("events")
    count = snapshot.get("event_count")
    if (snapshot.get("schema") != PUBLIC_SCHEMA
            or snapshot.get("provider") != PUBLIC_PROVIDER
            or snapshot.get("status") != "RESEARCH_ONLY"
            or snapshot.get("production_recommendations") != "DISABLED"
            or snapshot.get("market") != "h2h"
            or snapshot.get("raw_bookmaker_quotes_redistributed") is not False
            or snapshot.get("raw_bookmaker_names_redistributed") is not False
            or snapshot.get("model_value_advantage_verified") is not False
            or type(count) is not int or count < 0 or count > MAX_EVENTS
            or not isinstance(events, list) or len(events) != count
            or not all(_public_row_valid(row, as_of) for row in events)):
        return "INVALID_PUBLIC_SNAPSHOT", [], None
    if as_of > now:
        return "FUTURE_OR_INVALID_SNAPSHOT_TIME", [], as_of
    if (now - as_of).total_seconds() > MAX_CAPTURE_AGE_SECONDS:
        return "STALE_PUBLIC_SNAPSHOT", events, as_of
    return "FRESH_PUBLIC_RESEARCH_SNAPSHOT", events, as_of


def _read_bindings(bindings, fixture_ids):
    """Supplied binding is a claim, never an independent identity attestation."""
    if bindings is None:
        return "NO_BINDINGS", [], set()
    if not isinstance(bindings, list) or len(bindings) > 9:
        return "INVALID_BINDINGS", [], set()
    result = []
    for binding in bindings:
        if (not isinstance(binding, dict) or set(binding) != BINDING_FIELDS
                or not all(_id(binding.get(k)) for k in BINDING_FIELDS)
                or binding["local_request_id"] not in fixture_ids):
            return "INVALID_BINDINGS", [], set()
        result.append(binding)
    fixture_counts = Counter(b["local_request_id"] for b in result)
    native_counts = Counter((b["provider"], b["source_event_id"])
                            for b in result)
    collisions = {b["local_request_id"] for b in result
                  if fixture_counts[b["local_request_id"]] != 1
                  or native_counts[(b["provider"], b["source_event_id"])] != 1}
    return "UNAUTHENTICATED_BINDINGS", result, collisions


def audit(manifest, market_snapshot, *, bindings=None, now_utc=None,
          uefa_evidence=None):
    """Examine all nine fixtures with optional reviewed official match links.

    UEFA identifiers are independent of an odds provider's event IDs. No
    bookmakers, odds, executable offers or model certification are inferred.
    """
    fixtures = validate_manifest(manifest)
    now = _utc(datetime.now(timezone.utc) if now_utc is None else now_utc)
    official_links = {}
    official_evidence_state = "MISSING_OFFICIAL_MATCH_LINK_EVIDENCE"
    if uefa_evidence is not None:
        # Import only on demand; this module provides validate_manifest,
        # so module-level import would create a cycle.
        from ucl_official_match_identity import validate_official_links
        try:
            official_links = validate_official_links(uefa_evidence, manifest)
        except (ValueError, TypeError, OverflowError):
            official_evidence_state = "INVALID_OR_CONFLICTING_OFFICIAL_LINK_EVIDENCE"
        else:
            official_evidence_state = "REVIEWED_UEFA_LINKS_RECONCILED_OFFLINE"
    source_state, public_events, market_as_of = _read_public_snapshot(
        market_snapshot, now)
    binding_state, binding_rows, ambiguous = _read_bindings(
        bindings, {row["local_request_id"] for row in fixtures})
    ucl_rows = [row for row in public_events
                if row["league"] == UCL_SPORT_KEY]
    # A provider-native ID belongs to one event across its entire feed,
    # including domestic leagues; never isolate collisions to the UCL subset.
    native_id_counts = Counter(row["source_event_id"] for row in public_events)
    ucl_native_ids = {row["source_event_id"] for row in ucl_rows}
    group = {}
    for binding in binding_rows:
        group.setdefault(binding["local_request_id"], []).append(binding)
    records = []
    for fixture in fixtures:
        fid = fixture["local_request_id"]
        kickoff = _utc(fixture["kickoff_utc"])
        official = official_links.get(fid)
        blockers = []
        if official is None:
            blockers.append("UEFA_MATCH_LINK_EVIDENCE_UNAVAILABLE")
        complete_public_h2h = False
        if now >= kickoff:
            blockers.append("POST_KICKOFF_NO_NEW_PREMATCH_AUTHORIZATION")
        if source_state != "FRESH_PUBLIC_RESEARCH_SNAPSHOT":
            blockers.append(source_state)
        elif not ucl_rows:
            blockers.append("NO_UCL_EVENTS_IN_PUBLIC_SNAPSHOT")

        if binding_state == "INVALID_BINDINGS":
            blockers.append("INVALID_PROVIDER_BINDINGS")
        elif fid in ambiguous:
            blockers.append("AMBIGUOUS_PROVIDER_NATIVE_BINDING")
        elif not group.get(fid):
            blockers.append("NO_PROVIDER_NATIVE_EVENT_BINDING")
        elif source_state == "FRESH_PUBLIC_RESEARCH_SNAPSHOT" and now < kickoff:
            claim = group[fid][0]
            if (claim["provider"] != PUBLIC_PROVIDER
                    or claim["provider_sport_key"] != UCL_SPORT_KEY):
                blockers.append("NATIVE_EVENT_SOURCE_MISMATCH")
            else:
                native_id = claim["source_event_id"]
                if native_id_counts.get(native_id, 0) > 1:
                    blockers.append("DUPLICATE_PUBLIC_NATIVE_EVENT_ID")
                elif native_id not in ucl_native_ids:
                    blockers.append("NATIVE_EVENT_NOT_FOUND_IN_UCL_SCOPE")
                else:
                    source = next(row for row in ucl_rows
                                  if row["source_event_id"] == native_id)
                    if (source["home"] != fixture["home"]
                            or source["away"] != fixture["away"]
                            or _utc(source["kickoff_utc"]) != kickoff):
                        blockers.append("NATIVE_EVENT_FIXTURE_KICKOFF_MISMATCH")
                    elif (market_as_of - _utc(
                            source["market_last_update_utc"])).total_seconds(
                            ) > MAX_MARKET_UPDATE_AGE_SECONDS:
                        blockers.append("STALE_PUBLIC_MARKET_UPDATE")
                    else:
                        complete_public_h2h = True
        # Every one is still an untrusted structural observation (no raw quote).
        if complete_public_h2h:
            blockers.append("PUBLIC_H2H_CONSENSUS_NOT_EXECUTABLE_QUOTE")
        blockers.extend((
            "NO_INDEPENDENTLY_AUTHENTICATED_ATOMIC_BOOKMAKER_QUOTES",
            "NO_UCL_MARKET_MODEL_OUT_OF_SAMPLE_CALIBRATION",
            "NO_VERIFIED_LINEUP_USE_IN_SEALED_MODEL",
            "NO_SIGNED_MODEL_PROMOTION_AUTHORITY",
        ))
        records.append({
            "local_request_id": fid,
            "home": fixture["home"],
            "away": fixture["away"],
            "kickoff_utc": kickoff.isoformat(),
            "kickoff_hkt": kickoff.astimezone(
                timezone(timedelta(hours=8))).isoformat(),
            "status": "HOLD",
            "uefa_official_match_id": (official["uefa_match_id"]
                                       if official is not None else None),
            "uefa_official_match_url": (official["uefa_match_url"]
                                        if official is not None else None),
            "uefa_match_link_reviewed_offline": official is not None,
            "uefa_live_page_response_authenticated": False,
            "public_h2h_structural_observation": complete_public_h2h,
            "provider_identity_independently_verified": False,
            "atomic_bookmaker_markets_authenticated": [],
            "calibrated_market_models_available": [],
            "official_lineup_in_model_authenticated": False,
            "blockers": blockers,
            "bets_authorized": 0,
        })
    return {
        "schema": SCHEMA,
        "generated_utc": now.isoformat(),
        "status": "HOLD", "research_only": True,
        "manifest_fixture_source_url": manifest["fixture_source_url"],
        "schedule_is_not_provider_native_identity": True,
        "uefa_match_link_evidence_state": official_evidence_state,
        "uefa_official_match_links_reconciled": len(official_links),
        "uefa_urls_from_reviewed_static_source_not_live_api": True,
        "source_fixture_ids_independently_authenticated": False,
        "snapshot_state": source_state,
        "snapshot_as_of_utc": (market_as_of.isoformat()
                               if market_as_of is not None else None),
        "binding_state": binding_state,
        "fixtures_expected": len(fixtures),
        "observed_ucl_events_in_public_snapshot": (
            len(ucl_rows) if source_state == "FRESH_PUBLIC_RESEARCH_SNAPSHOT"
            else 0),
        "fixtures_with_structurally_matched_public_h2h": sum(
            x["public_h2h_structural_observation"] for x in records),
        "fixtures_with_verified_betting_quotes": 0,
        "asian_handicap_quotes_authenticated": False,
        "corners_quotes_authenticated": False,
        "first_half_goals_quotes_authenticated": False,
        "calibrated_prediction_probabilities_verified": False,
        "independent_forward_result_validation_passed": False,
        "needed_market_types": list(REQUIRED_MARKETS),
        "fixtures": records,
        "bets_authorized": 0,
        "production_recommendations": "DISABLED",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=(
        "config/ucl_md4_2026_11_03_nine_fixtures.json"))
    parser.add_argument("--market", default="market/latest.json")
    parser.add_argument("--bindings", default=None)
    parser.add_argument("--uefa-evidence", default=None,
                        help="Reviewed official link evidence JSON, not odds IDs")
    parser.add_argument("--output", default="artifacts/ucl_md4_nine_coverage.json")
    parser.add_argument("--now-utc", default=None,
                        help="Optional deterministic UTC audit instant (tests only)")
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    market = json.loads(Path(args.market).read_text(encoding="utf-8"))
    bindings = (None if args.bindings is None else
                json.loads(Path(args.bindings).read_text(encoding="utf-8")))
    uefa_evidence = (None if args.uefa_evidence is None else
                     json.loads(Path(args.uefa_evidence).read_text(encoding="utf-8")))
    result = audit(manifest, market, bindings=bindings, now_utc=args.now_utc,
                   uefa_evidence=uefa_evidence)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("UCL_NINE_AUDIT:", result["status"],
          "FIXTURES:", result["fixtures_expected"],
          "STRUCTURAL_H2H:", result["fixtures_with_structurally_matched_public_h2h"],
          "UEFA_LINKS:", result["uefa_official_match_links_reconciled"],
          "VERIFIED_QUOTES:", result["fixtures_with_verified_betting_quotes"],
          "PRODUCTION:", result["production_recommendations"])


if __name__ == "__main__":
    main()
