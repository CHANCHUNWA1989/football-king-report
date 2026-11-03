"""Zero-network verification of UEFA/UCL event catalogue and token safety."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ops"))
from ucl_zero_credit_event_catalogue import (
    API_ENDPOINT, SPORT_KEY, audit_events, collect, _fetch_events,
)

MANIFEST = json.loads((ROOT / "config/ucl_md4_2026_11_03_nine_fixtures.json")
                      .read_text(encoding="utf-8"))
EVIDENCE = json.loads((ROOT / "config/ucl_md4_2026_11_03_uefa_match_links.json")
                      .read_text(encoding="utf-8"))
NOW = "2026-11-03T11:00:00Z"
PRIVATE_KEY = "PRIVATE_FAKE_API_KEY_FOR_TESTS"


def event(index=0, native_id="a" * 32):
    f = MANIFEST["fixtures"][index]
    return {
        "id": native_id,
        "sport_key": SPORT_KEY,
        "sport_title": "UEFA Champions League",
        "commence_time": f["kickoff_utc"],
        "home_team": f["home"],
        "away_team": f["away"],
    }


class Reply:
    def __init__(self, request, payload, *, last="0", used="44",
                 remaining="456", status=200, other_url=None):
        self.url = request.full_url if other_url is None else other_url
        self.status = status
        self.headers = {
            "x-requests-last": last, "x-requests-used": used,
            "x-requests-remaining": remaining,
        }
        self.payload = (payload if isinstance(payload, bytes)
                        else json.dumps(payload).encode("utf-8"))
        self.read_calls = 0

    def geturl(self):
        return self.url

    def read(self, maximum):
        self.read_calls += 1
        return self.payload[:maximum]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def opener_for(data, *, headers=None, status=200, redirect=None,
               seen=None):
    def open_stub(request, timeout):
        if seen is not None:
            seen.append((request.full_url, timeout))
        return Reply(request, data, status=status, other_url=redirect,
                     **(headers or {}))
    return open_stub


class UclZeroCreditEventCatalogueTests(unittest.TestCase):
    def test_no_secret_does_not_make_network_request(self):
        calls = []
        out = collect(MANIFEST, EVIDENCE, api_key=None,
                      now_utc=NOW, opener=opener_for([event()], seen=calls))
        self.assertEqual(calls, [])
        self.assertEqual(out["catalogue_state"], "MISSING_GITHUB_SECRET")
        self.assertEqual(out["fixtures_with_exact_native_id_candidates"], 0)
        self.assertEqual(out["uefa_official_links_reconciled"], 9)
        self.assertFalse(out["provider_request_attempted"])

    def test_one_real_schema_event_is_structural_candidate_not_betting(self):
        calls = []
        out = collect(MANIFEST, EVIDENCE, api_key=PRIVATE_KEY,
                      now_utc=NOW, opener=opener_for([event()], seen=calls))
        self.assertEqual(len(calls), 1)
        url, timeout = calls[0]
        self.assertEqual(urlsplit(url).scheme, "https")
        self.assertEqual(urlsplit(url).netloc, "api.the-odds-api.com")
        self.assertEqual(urlsplit(url).path, urlsplit(API_ENDPOINT).path)
        self.assertNotIn("/odds", urlsplit(url).path)
        self.assertNotIn("/markets", urlsplit(url).path)
        self.assertEqual(parse_qs(urlsplit(url).query)["commenceTimeFrom"],
                         ["2026-11-03T17:45:00Z"])
        self.assertEqual(timeout, 12)
        self.assertEqual(out["fixtures_with_exact_native_id_candidates"], 1)
        self.assertEqual(out["catalogue_event_rows"], 1)
        # Offline injected HTTP replies must never impersonate a live vendor.
        self.assertFalse(out["quota_cost_verified_zero"])
        self.assertFalse(out["source_live_http_origin_checked"])
        self.assertFalse(out["provider_request_attempted"])
        self.assertEqual(out["source_provenance"], "TEST_DOUBLE_INJECTED")
        self.assertTrue(out["provider_zero_cost_header_shape_passed"])
        self.assertEqual(out["fixtures_with_independently_verified_native_ids"], 0)
        self.assertEqual(out["fixtures_with_authenticated_bookmaker_quotes"], 0)
        self.assertEqual(out["bets_authorized"], 0)
        self.assertEqual(out["production_recommendations"], "DISABLED")
        self.assertTrue(all(row["status"] == "HOLD" for row in out["fixtures"]))
        self.assertNotIn(PRIVATE_KEY, json.dumps(out))
        self.assertNotIn("a" * 32, json.dumps(out))

    def test_nine_unique_exact_matches_still_unverified(self):
        rows = [event(i, f"{i+1:032x}") for i in range(9)]
        report, private_map = audit_events(MANIFEST, EVIDENCE, rows=rows,
                                           now_utc=NOW)
        self.assertEqual(report["fixtures_with_exact_native_id_candidates"], 9)
        self.assertEqual(len(private_map), 9)
        self.assertEqual(report["fixtures_with_independently_verified_native_ids"], 0)
        self.assertEqual(report["status"], "HOLD")
        self.assertTrue(all(row["provider_event_id_candidate_present"]
                            for row in report["fixtures"]))
        for native_id in private_map.values():
            self.assertNotIn(native_id, json.dumps(report))

    def test_no_fuzzy_or_reversed_team_matching(self):
        for change in ("reversed", "wrong_name", "wrong_day", "wrong_time"):
            item = event()
            if change == "reversed":
                item["home_team"], item["away_team"] = (
                    item["away_team"], item["home_team"])
            elif change == "wrong_name":
                item["home_team"] = "Unverified Other Team"
            elif change == "wrong_day":
                item["commence_time"] = "2026-11-04T17:45:00Z"
            elif change == "wrong_time":
                item["commence_time"] = "2026-11-03T17:45:01Z"
            report, ids = audit_events(MANIFEST, EVIDENCE, rows=[item],
                                       now_utc=NOW)
            with self.subTest(change=change):
                self.assertEqual(len(ids), 0)
                self.assertEqual(report["fixtures_with_exact_native_id_candidates"], 0)

    def test_ambiguous_two_native_ids_for_one_match_fail_closed(self):
        rows = [event(native_id="a" * 32), event(native_id="b" * 32)]
        result, ids = audit_events(MANIFEST, EVIDENCE, rows=rows,
                                   now_utc=NOW)
        self.assertEqual(ids, {})
        self.assertIn("AMBIGUOUS_IDENTICAL_FIXTURE_NATIVE_EVENTS",
                      result["fixtures"][0]["blockers"])

    def test_duplicate_native_id_anywhere_poison_entire_catalogue(self):
        rows = [event(), event(index=1)]
        result, ids = audit_events(MANIFEST, EVIDENCE, rows=rows,
                                   now_utc=NOW)
        self.assertEqual(ids, {})
        self.assertEqual(result["catalogue_state"],
                         "INVALID_OR_CONFLICTING_PROVIDER_EVENTS")
        self.assertEqual(result["catalogue_event_rows"], 0)

    def test_uefa_page_id_is_not_the_odds_api_id(self):
        item = event(native_id="2049613")
        result, ids = audit_events(MANIFEST, EVIDENCE, rows=[item],
                                   now_utc=NOW)
        self.assertEqual(ids, {})
        self.assertEqual(result["catalogue_event_rows"], 0)

    def test_wrong_sport_malformed_fields_and_pricing_are_rejected(self):
        cases = [
            {"sport_key": "soccer_epl"},
            {"id": "NOT_VALID_ID"},
            {"id": True},
            {"id": []},
            {"home_team": ""},
            {"away_team": "Shakhtar Donetsk"},
            {"bookmakers": [{"key": "fake", "price": 1.92}]},
            {"odds": 1.87},
            {"commence_time": "2026-11-03T17:45:00"},
            {"commence_time": None},
            {"home_rotation_number": True},
        ]
        for change in cases:
            row = event()
            row.update(change)
            with self.subTest(change=change):
                result, ids = audit_events(MANIFEST, EVIDENCE, rows=[row],
                                           now_utc=NOW)
                self.assertEqual(len(ids), 0)
                self.assertEqual(result["catalogue_state"],
                                 "INVALID_OR_CONFLICTING_PROVIDER_EVENTS")

    def test_quota_nonzero_or_missing_headers_are_quarantined(self):
        for headers in ({"last": "1"}, {"last": None},
                        {"used": None}, {"remaining": None}):
            calls = []
            report = collect(
                MANIFEST, EVIDENCE, api_key=PRIVATE_KEY, now_utc=NOW,
                opener=opener_for([event()], headers=headers, seen=calls))
            with self.subTest(headers=headers):
                self.assertEqual(len(calls), 1)
                self.assertEqual(report["catalogue_state"],
                                 "ZERO_COST_NOT_ATTESTED_BY_VENDOR")
                self.assertFalse(report["quota_cost_verified_zero"])
                self.assertEqual(report["fixtures_with_exact_native_id_candidates"], 0)

    def test_unexpected_redirect_and_status_rejected(self):
        for status, redirect in ((200, "https://evil.example/sink"),
                                 (301, None), (404, None)):
            report = collect(
                MANIFEST, EVIDENCE, api_key=PRIVATE_KEY, now_utc=NOW,
                opener=opener_for([event()], status=status, redirect=redirect))
            with self.subTest(status=status, redirect=redirect):
                self.assertEqual(report["catalogue_state"],
                                 "UNEXPECTED_PROVIDER_ORIGIN_OR_STATUS")
                self.assertEqual(report["fixtures_with_exact_native_id_candidates"], 0)

    def test_request_error_does_not_expose_api_key_in_report(self):
        def throw_secret(request, timeout):
            raise HTTPError(request.full_url, 403, "PRIVATE_ERROR", {}, None)
        report = collect(MANIFEST, EVIDENCE, api_key=PRIVATE_KEY, now_utc=NOW,
                         opener=throw_secret)
        self.assertEqual(report["catalogue_state"], "PROVIDER_HTTP_403")
        self.assertNotIn(PRIVATE_KEY, json.dumps(report))

    def test_no_events_is_eligible_zero_cost_but_not_coverage(self):
        out = collect(MANIFEST, EVIDENCE, api_key=PRIVATE_KEY,
                      now_utc=NOW, opener=opener_for([]))
        self.assertFalse(out["quota_cost_verified_zero"])
        self.assertTrue(out["provider_zero_cost_header_shape_passed"])
        self.assertFalse(out["provider_request_attempted"])
        self.assertEqual(out["catalogue_state"], "NO_PROVIDER_EVENTS_RETURNED")
        self.assertEqual(out["fixtures_with_exact_native_id_candidates"], 0)
        self.assertFalse(out["provider_current_season_entitlement_verified"])

    def test_bad_provider_json_and_duplicate_keys_rejected(self):
        payloads = [
            b'not json',
            b'[{"id":"bad","id":"duplicated"}]',
            b'{"data":[]}',
            b'[' + b'x' * 600001 + b']',
        ]
        for payload in payloads:
            report = collect(MANIFEST, EVIDENCE, api_key=PRIVATE_KEY,
                             now_utc=NOW, opener=opener_for(payload))
            with self.subTest(payload_size=len(payload)):
                self.assertEqual(report["fixtures_with_exact_native_id_candidates"], 0)
                self.assertIn(report["catalogue_state"],
                              ("INVALID_PROVIDER_EVENT_RESPONSE",
                               "OVERSIZE_PROVIDER_CATALOGUE"))

    def test_missing_or_fake_official_evidence_prevents_fetch(self):
        broken = copy.deepcopy(EVIDENCE)
        broken["links"][0]["uefa_match_id"] = "2049999"
        calls = []
        with self.assertRaises(ValueError):
            collect(MANIFEST, broken, api_key=PRIVATE_KEY, now_utc=NOW,
                    opener=opener_for([event()], seen=calls))
        self.assertEqual(calls, [])

    def test_invalid_secret_does_not_attempt_network_or_claim_vendor_request(self):
        calls = []
        for bad in ("invalid key with spaces", "bad\\nsecret", "測試密鑰"):
            out = collect(MANIFEST, EVIDENCE, api_key=bad,
                          now_utc=NOW, opener=opener_for([event()], seen=calls))
            with self.subTest(bad="REDACTED"):
                self.assertEqual(out["catalogue_state"],
                                 "MISSING_OR_INVALID_GITHUB_SECRET")
                self.assertFalse(out["provider_request_attempted"])
                self.assertFalse(out["source_live_http_origin_checked"])
                self.assertFalse(out["quota_cost_verified_zero"])
        self.assertEqual(calls, [])

    def test_direct_supplied_rows_cannot_self_claim_https_vendor_provenance(self):
        report, _ = audit_events(MANIFEST, EVIDENCE, rows=[event()],
                                 now_utc=NOW)
        self.assertEqual(report["source_provenance"], "OFFLINE_SUPPLIED")
        self.assertFalse(report["source_live_http_origin_checked"])
        self.assertFalse(report["quota_cost_verified_zero"])

    def test_after_all_kickoffs_no_requests_or_new_prematch_candidates(self):
        calls = []
        report = collect(MANIFEST, EVIDENCE, api_key=PRIVATE_KEY,
                         now_utc="2026-11-03T20:00:01Z",
                         opener=opener_for([event()], seen=calls))
        self.assertEqual(calls, [])
        self.assertEqual(report["catalogue_state"], "ALL_NINE_KICKOFFS_PASSED")
        self.assertEqual(report["fixtures_with_exact_native_id_candidates"], 0)

    def test_inplay_fixture_candidate_does_not_get_new_prematch_identity(self):
        report, private_map = audit_events(
            MANIFEST, EVIDENCE, rows=[event()],
            now_utc="2026-11-03T18:00:00Z")
        self.assertNotIn(MANIFEST["fixtures"][0]["local_request_id"], private_map)
        self.assertFalse(report["fixtures"][0]["provider_event_id_candidate_present"])
        self.assertIn("ALREADY_STARTED_NO_NEW_PREMATCH_VALIDATION",
                      report["fixtures"][0]["blockers"])

    def test_reject_massive_or_malformed_catalogues(self):
        payloads = ([event()] * 251, "bad", {}, [42], [None], [True])
        for payload in payloads:
            with self.subTest(type=type(payload).__name__):
                result, ids = audit_events(MANIFEST, EVIDENCE, rows=payload,
                                           now_utc=NOW)
                self.assertEqual(ids, {})
                self.assertEqual(result["catalogue_state"],
                                 "INVALID_OR_CONFLICTING_PROVIDER_EVENTS")


if __name__ == "__main__":
    unittest.main()
