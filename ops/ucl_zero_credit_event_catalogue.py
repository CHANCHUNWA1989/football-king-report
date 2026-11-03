"""The Odds API UCL zero-credit EVENTS catalogue; no odds or public native IDs.

Official v4 docs: GET /v4/sports/{sport}/events does not use quota credits.
One optional authenticated metadata request (never odds/markets/scores).
GitHub PR CI runs OFFLINE without secrets; live request is manual on main only.

A structurally matched native event ID is only an *unverified candidate*; it
never certifies source entitlement, independent identity, bookmaker prices,
calibrated EV, or any authority to make betting recommendations.
"""
import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, HTTPRedirectHandler, build_opener

from ucl_md4_nine_fixture_coverage import validate_manifest, _utc
from ucl_official_match_identity import validate_official_links

SCHEMA = "football-king-ucl-zero-credit-native-event-catalogue-v1"
SPORT_KEY = "soccer_uefa_champs_league"
API_ENDPOINT = "https://api.the-odds-api.com/v4/sports/" + SPORT_KEY + "/events"
MAX_BYTES = 600_000
MAX_EVENTS = 250
EVENT_FIELDS = frozenset((
    "id", "sport_key", "sport_title", "commence_time",
    "home_team", "away_team", "home_rotation_number",
    "away_rotation_number",
))
REQUIRED_FIELDS = frozenset((
    "id", "sport_key", "commence_time", "home_team", "away_team",
))
FETCH_FROM = "2026-11-03T17:45:00Z"
FETCH_TO = "2026-11-03T20:00:00Z"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        # apiKey lives in the query string; NEVER follow redirected URLs.
        return None


def _identity(text):
    return (isinstance(text, str) and 0 < len(text.strip()) <= 128
            and all(32 <= ord(char) != 127 for char in text))


def _unique_json(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY")
        out[key] = value
    return out


def _validate_catalogue(rows):
    if not isinstance(rows, list) or len(rows) > MAX_EVENTS:
        raise ValueError("BAD_EVENT_BATCH")
    native_ids = set()
    safe = []
    for item in rows:
        if (not isinstance(item, dict)
                or not REQUIRED_FIELDS <= set(item)
                or not set(item) <= EVENT_FIELDS):
            raise ValueError("BAD_EVENT_SCHEMA")
        eid = item["id"]
        if (not isinstance(eid, str)
                or re.fullmatch(r"[0-9a-f]{32}", eid) is None
                or eid in native_ids
                or item["sport_key"] != SPORT_KEY
                or not _identity(item["home_team"])
                or not _identity(item["away_team"])
                or item["home_team"].casefold() == item["away_team"].casefold()
                or ("sport_title" in item
                    and not _identity(item["sport_title"]))):
            raise ValueError("BAD_OR_DUPLICATE_NATIVE_ID")
        # Rotation numbers are optional provider metadata, not identity.
        for field in ("home_rotation_number", "away_rotation_number"):
            if field in item and (type(item[field]) is not int
                                  or not 0 <= item[field] <= 100000):
                raise ValueError("INVALID_ROTATION_METADATA")
        try:
            instant = _utc(item["commence_time"])
        except (ValueError, TypeError, OverflowError):
            raise ValueError("INVALID_PROVIDER_KICKOFF") from None
        native_ids.add(eid)
        safe.append((eid, item["home_team"], item["away_team"], instant))
    return safe


def audit_events(manifest, official_evidence, rows=None, *,
                 now_utc=None):
    """Return sanitized 9-fixture report and EPHEMERAL private ID crosswalk.

    The second return value contains provider IDs and MUST NEVER be written
    to public JSON, job logs, GitHub commits or user-facing output.
    """
    fixtures = validate_manifest(manifest)
    reviewed = validate_official_links(official_evidence, manifest)
    now = _utc(datetime.now(timezone.utc) if now_utc is None else now_utc)
    try:
        native_rows = _validate_catalogue([] if rows is None else rows)
    except ValueError:
        native_rows, reason = [], "INVALID_OR_CONFLICTING_PROVIDER_EVENTS"
    else:
        reason = ("NO_PROVIDER_EVENTS_RETURNED" if not native_rows
                  else "PROVIDER_EVENTS_UNVERIFIED_CANDIDATES")
    in_day = [item for item in native_rows
              if item[3].date().isoformat() == "2026-11-03"]
    rows_at_kickoff = Counter(item[3] for item in in_day)
    results, private_crosswalk = [], {}
    for fixture in fixtures:
        case_id = fixture["local_request_id"]
        kickoff = _utc(fixture["kickoff_utc"])
        matching = [
            item for item in in_day
            if item[3] == kickoff
            and item[1] == fixture["home"]
            and item[2] == fixture["away"]
        ]
        blockers = []
        if now >= kickoff:
            blockers.append("ALREADY_STARTED_NO_NEW_PREMATCH_VALIDATION")
        if reason == "INVALID_OR_CONFLICTING_PROVIDER_EVENTS":
            blockers.append(reason)
        elif len(matching) > 1:
            blockers.append("AMBIGUOUS_IDENTICAL_FIXTURE_NATIVE_EVENTS")
        elif not matching:
            blockers.append("NO_EXACT_SCOPED_NATIVE_EVENT")
            if rows_at_kickoff[kickoff] > 0:
                blockers.append("SAME_KICKOFF_REQUIRES_MANUAL_TEAM_ID_REVIEW")
        elif now < kickoff:
            # Candidate ID retained only within process memory, not in report.
            private_crosswalk[case_id] = matching[0][0]
            blockers.append("NATIVE_EVENT_ID_CANDIDATE_NOT_INDEPENDENTLY_ATTESTED")
        else:
            blockers.append("INPLAY_EVENT_IS_NOT_NEW_PREMATCH_EVIDENCE")
        blockers.extend((
            "NO_AUTHENTICATED_BOOKMAKER_QUOTES",
            "NO_UCL_MARKET_DISTRIBUTION_CALIBRATION",
            "NO_INDEPENDENT_MODEL_PROMOTION_APPROVAL",
        ))
        results.append({
            "local_request_id": case_id,
            "uefa_official_match_id": reviewed[case_id]["uefa_match_id"],
            "kickoff_utc": kickoff.isoformat(),
            "provider_event_id_candidate_present": case_id in private_crosswalk,
            "provider_event_id_disclosed": False,
            "provider_native_fixture_identity_independently_verified": False,
            "actual_quote_verified": False,
            "status": "HOLD",
            "blockers": blockers,
            "bets_authorized": 0,
        })
    report = {
        "schema": SCHEMA,
        "generated_utc": now.isoformat(),
        "status": "HOLD",
        "research_only": True,
        "source_endpoint_without_credential": API_ENDPOINT,
        "source_provenance": "OFFLINE_SUPPLIED",
        "source_live_http_origin_checked": False,
        "provider_zero_cost_header_shape_passed": False,
        "provider_current_season_entitlement_verified": False,
        "provider_raw_event_ids_persisted": False,
        "uefa_official_links_reconciled": len(reviewed),
        "catalogue_state": reason,
        "catalogue_event_rows": len(native_rows),
        "catalogue_events_for_2026_11_03": len(in_day),
        "fixtures_expected": len(fixtures),
        "fixtures_with_exact_native_id_candidates": len(private_crosswalk),
        "fixtures_with_independently_verified_native_ids": 0,
        "fixtures_with_authenticated_bookmaker_quotes": 0,
        "quota_cost_verified_zero": False,
        "provider_request_attempted": False,
        "fixtures": results,
        "bets_authorized": 0,
        "production_recommendations": "DISABLED",
    }
    return report, private_crosswalk


def _fetch_events(secret, *, opener=None):
    """One single zero-odds endpoint request; no redirection, retry or logging.

    Any bad response including nonzero/missing provider quota metadata is
    quarantined. Never include exception strings (which might contain apiKey).
    """
    if not isinstance(secret, str) or not secret or any(
            ord(c) < 33 or ord(c) > 126 for c in secret):
        return None, "MISSING_OR_INVALID_SECRET", False
    params = urlencode({
        "apiKey": secret,
        "commenceTimeFrom": FETCH_FROM,
        "commenceTimeTo": FETCH_TO,
        "dateFormat": "iso",
    })
    request = Request(API_ENDPOINT + "?" + params, headers={
        "Accept": "application/json",
        "User-Agent": "FootballKingUCLZeroCreditResearch/1.0",
    })
    # A custom opener is for injected offline test doubles, NOT user URLs.
    call = opener if opener is not None else build_opener(NoRedirect()).open
    try:
        with call(request, timeout=12) as response:
            if (type(response.status) is not int or response.status != 200
                    or response.geturl() != request.full_url):
                return None, "UNEXPECTED_PROVIDER_ORIGIN_OR_STATUS", False
            cost = response.headers.get("x-requests-last")
            used = response.headers.get("x-requests-used")
            remaining = response.headers.get("x-requests-remaining")
            # A successful response with missing quota headers is not
            # sufficient evidence of zero-credit use.
            if (cost != "0" or used is None or remaining is None
                    or not str(used).isdigit()
                    or not str(remaining).isdigit()):
                return None, "ZERO_COST_NOT_ATTESTED_BY_VENDOR", False
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return None, "OVERSIZE_PROVIDER_CATALOGUE", False
        data = json.loads(raw, object_pairs_hook=_unique_json)
        _validate_catalogue(data)
        return data, "ZERO_COST_EVENT_RESPONSE_ACCEPTED", True
    except HTTPError as err:
        # Never print err or err.url: the URL embeds the secret.
        return None, "PROVIDER_HTTP_" + str(err.code), False
    except (URLError, TimeoutError, OSError):
        return None, "PROVIDER_NETWORK_FAILURE", False
    except (TypeError, AttributeError, ValueError, UnicodeError,
            json.JSONDecodeError, OverflowError):
        return None, "INVALID_PROVIDER_EVENT_RESPONSE", False


def collect(manifest, official_evidence, *, api_key=None,
            now_utc=None, opener=None):
    """Collect only metadata, and return ONLY sanitized public summary."""
    fixtures = validate_manifest(manifest)
    validate_official_links(official_evidence, manifest)
    now = _utc(datetime.now(timezone.utc) if now_utc is None else now_utc)
    if now >= max(_utc(f["kickoff_utc"]) for f in fixtures):
        out, _ = audit_events(manifest, official_evidence,
                              now_utc=now)
        out["catalogue_state"] = "ALL_NINE_KICKOFFS_PASSED"
        return out
    if not api_key:
        out, _ = audit_events(manifest, official_evidence,
                              now_utc=now)
        out["catalogue_state"] = "MISSING_GITHUB_SECRET"
        return out
    if (not isinstance(api_key, str) or any(
            ord(ch) < 33 or ord(ch) > 126 for ch in api_key)):
        out, _ = audit_events(manifest, official_evidence,
                              now_utc=now)
        out["catalogue_state"] = "MISSING_OR_INVALID_GITHUB_SECRET"
        return out
    payload, state, zero_header = _fetch_events(api_key, opener=opener)
    # The bounded HTTP call can cross a match's kickoff. Never reuse the
    # pre-request timestamp to describe *post-response* pre-match eligibility.
    # Deterministic now_utc is reserved for offline tests; production re-reads
    # the actual clock immediately after the network response has completed.
    response_completed_at = _utc(
        datetime.now(timezone.utc) if now_utc is None else now_utc)
    report, _private = audit_events(
        manifest, official_evidence, rows=payload, now_utc=response_completed_at)
    # An injected opener is an offline test double, never a genuine authenticated
    # call to the upstream. Its synthetic quota headers cannot certify spend.
    real_call = opener is None
    report["provider_request_attempted"] = real_call
    report["quota_cost_verified_zero"] = real_call and zero_header
    report["provider_zero_cost_header_shape_passed"] = zero_header
    report["source_provenance"] = (
        "HTTPS_ORIGIN_CHECKED" if real_call and zero_header
        else "PROVIDER_CALL_UNVERIFIED" if real_call
        else "TEST_DOUBLE_INJECTED")
    report["source_live_http_origin_checked"] = real_call and zero_header
    if not zero_header:
        report["catalogue_state"] = state
    # In-memory native IDs are deliberately discarded until a separate
    # authorized provider quote workflow consumes them in one trusted process.
    return report


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--manifest",
                   default="config/ucl_md4_2026_11_03_nine_fixtures.json")
    p.add_argument("--uefa-evidence",
                   default="config/ucl_md4_2026_11_03_uefa_match_links.json")
    p.add_argument("--output",
                   default="artifacts/ucl_md4_zero_credit_catalogue.json")
    p.add_argument("--offline", action="store_true",
                   help="Only run offline zero-network coverage; no key used")
    a = p.parse_args(argv)
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    evidence = json.loads(Path(a.uefa_evidence).read_text(encoding="utf-8"))
    report = collect(
        manifest, evidence,
        api_key=None if a.offline else os.environ.get("THE_ODDS_API_KEY"))
    target = Path(a.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("UCL_EVENT_CATALOGUE:", report["catalogue_state"],
          "UEFA_MATCHES:", report["uefa_official_links_reconciled"],
          "NATIVE_CANDIDATES:", report["fixtures_with_exact_native_id_candidates"],
          "ZERO_CREDIT_VERIFIED:", report["quota_cost_verified_zero"],
          "PRODUCTION:", report["production_recommendations"])


if __name__ == "__main__":
    main()
