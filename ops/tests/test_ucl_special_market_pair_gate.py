"""Zero-network negative/positive tests for UCL special-market quote coverage."""
import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucl_special_market_pair_gate import audit, SCHEMA

NOW = "2026-11-03T19:00:00Z"
FEY = "ucl26m4-feyenoord-inter"
BAR = "ucl26m4-barcelona-villa"


def quote(*, case=FEY, book="PRIVATE_BOOK_FOO"):
    home, away, market, line = (
        ("Feyenoord", "Inter", "corners_total", 9.0) if case == FEY
        else ("Barcelona", "Aston Villa", "first_half_goals", 1.75)
    )
    return {
        "case_id": case, "fixture": {
            "home": home, "away": away,
            "kickoff_utc": "2026-11-03T20:00:00+00:00",
        },
        "provider": "TEST_PRIVATE_SOURCE",
        "provider_event_id": "NATIVE_TEST_EVENT_F" if case == FEY else "NATIVE_TEST_EVENT_B",
        "bookmaker_id": book, "market_id": market,
        "market_updated_utc": "2026-11-03T18:59:40Z",
        "captured_utc": "2026-11-03T18:59:48Z",
        "outcomes": [
            {"selection": "OVER", "line": line, "decimal_odds": 1.98},
            {"selection": "UNDER", "line": line, "decimal_odds": 1.88},
        ],
    }


class UclAtomicSpecialMarketTests(unittest.TestCase):
    def test_no_inputs_is_hold_no_coverage(self):
        result = audit(now_utc=NOW)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["structurally_valid_pairs"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["bets_authorized"], 0)
        self.assertTrue(all(case["state"] == "HOLD_NO_VALID_ATOMIC_PAIR"
                            for case in result["cases"]))

    def test_two_atomic_synthetic_pairs_are_structurally_complete_only(self):
        result = audit([quote(), quote(case=BAR)], now_utc=NOW)
        self.assertEqual(result["structurally_valid_pairs"], 2)
        self.assertEqual(result["submitted_blocks"], 2)
        self.assertEqual([c["market"] for c in result["cases"]],
                         ["corners_total", "first_half_goals"])
        self.assertTrue(all(c["state"] == "RESEARCH_ONLY_ATOMIC_PAIR_UNAUTHENTICATED"
                            for c in result["cases"]))
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["actual_quote_execution_authenticated"])
        self.assertFalse(result["market_bookmaker_provenance_independently_verified"])
        output = json.dumps(result)
        for forbidden in ("PRIVATE_BOOK_FOO", "TEST_PRIVATE_SOURCE",
                          "NATIVE_TEST_EVENT_F", "1.98", "1.88"):
            self.assertNotIn(forbidden, output)

    def test_asian_spread_is_other_engine_scope(self):
        raw = quote()
        raw["case_id"] = "ucl26m4-atletico-bayern"
        result = audit([raw], now_utc=NOW)
        self.assertEqual(result["structurally_valid_pairs"], 0)
        self.assertEqual(result["rejection_counts"]["UNSUPPORTED_CASE"], 1)

    def test_wrong_market_period_is_not_full_time_total(self):
        raw = quote(case=BAR)
        raw["market_id"] = "totals"
        result = audit([raw], now_utc=NOW)
        self.assertEqual(result["rejection_counts"]["WRONG_MARKET_PERIOD_OR_CATEGORY"], 1)

    def test_no_cross_book_stitching(self):
        a = quote()
        b = quote(book="OTHER_BOOK")
        a["outcomes"] = a["outcomes"][:1]
        b["outcomes"] = b["outcomes"][1:]
        result = audit([a, b], now_utc=NOW)
        self.assertEqual(result["structurally_valid_pairs"], 0)
        self.assertEqual(result["rejection_counts"]["INCOMPLETE_ATOMIC_PAIR"], 2)

    def test_duplicate_bookmaker_poison_both_even_if_one_bad(self):
        a, b = quote(), quote()
        b["outcomes"] = b["outcomes"][:1]
        result = audit([a, b], now_utc=NOW)
        self.assertEqual(result["structurally_valid_pairs"], 0)
        self.assertEqual(result["rejection_counts"]["DUPLICATE_BOOKMAKER_CASE"], 2)

    def test_market_line_not_rounded_or_inferred(self):
        for wrong in (8.75, 9.25, True, float("nan"), 9.00000001):
            raw = quote()
            raw["outcomes"][1]["line"] = wrong
            with self.subTest(wrong=wrong):
                result = audit([raw], now_utc=NOW)
                self.assertEqual(result["rejection_counts"]["MISMATCHED_REQUESTED_LINE"], 1)

    def test_over_and_under_duplicate_side_rejected(self):
        raw = quote()
        raw["outcomes"][1]["selection"] = "OVER"
        result = audit([raw], now_utc=NOW)
        self.assertEqual(result["rejection_counts"]["INCOMPLETE_OR_DUPLICATE_SIDE"], 1)

    def test_source_native_event_id_cannot_bind_two_fixtures(self):
        a, b = quote(), quote(case=BAR)
        b["provider_event_id"] = a["provider_event_id"]
        result = audit([a, b], now_utc=NOW)
        self.assertEqual(result["structurally_valid_pairs"], 0)
        self.assertEqual(result["rejection_counts"]["AMBIGUOUS_NATIVE_EVENT_ID"], 2)

    def test_native_event_ids_are_namespaced_per_provider(self):
        a = quote()
        b = quote(case=BAR)
        b["provider"] = "ANOTHER_PROVIDER"
        b["provider_event_id"] = a["provider_event_id"]
        report = audit([a, b], now_utc=NOW)
        self.assertEqual(report["structurally_valid_pairs"], 2)
        self.assertNotIn("AMBIGUOUS_NATIVE_EVENT_ID", report["rejection_counts"])

    def test_fixture_and_native_ids_do_not_override_request_identity(self):
        raw = quote()
        raw["fixture"]["home"] = "Fake Feyenoord"
        result = audit([raw], now_utc=NOW)
        self.assertEqual(result["rejection_counts"]["FIXTURE_IDENTITY_OR_KICKOFF_MISMATCH"], 1)

    def test_old_capture_old_market_and_future_quote_all_hold(self):
        raw = quote()
        raw["market_updated_utc"] = "2026-11-03T18:30:00Z"
        raw["captured_utc"] = "2026-11-03T18:30:01Z"
        self.assertIn("STALE_CAPTURE", audit([raw], now_utc=NOW)["rejection_counts"])
        raw = quote()
        raw["market_updated_utc"] = "2026-11-03T18:30:00Z"
        self.assertIn("STALE_MARKET_UPDATE",
                      audit([raw], now_utc=NOW)["rejection_counts"])
        raw = quote()
        raw["market_updated_utc"] = "2026-11-03T19:00:01Z"
        self.assertIn("INVALID_CHRONOLOGY",
                      audit([raw], now_utc=NOW)["rejection_counts"])

    def test_match_started_or_too_close_rejected(self):
        self.assertIn("TOO_CLOSE_TO_KICKOFF",
                      audit([quote()], now_utc="2026-11-03T19:55:00Z")["rejection_counts"])
        self.assertIn("INVALID_CHRONOLOGY",
                      audit([quote()], now_utc="2026-11-03T20:00:01Z")["rejection_counts"])

    def test_bad_odds_and_noncanonical_outcomes(self):
        for bad in (1.0, True, float("nan"), 101):
            raw = quote()
            raw["outcomes"][0]["decimal_odds"] = bad
            self.assertIn("INVALID_DECIMAL_ODDS",
                          audit([raw], now_utc=NOW)["rejection_counts"])
        raw = quote()
        raw["outcomes"][0]["decimal_odds"] = 10 ** 1000
        self.assertIn("INVALID_DECIMAL_ODDS",
                      audit([raw], now_utc=NOW)["rejection_counts"])
        raw = quote()
        raw["outcomes"][1]["line"] = 10 ** 1000
        self.assertIn("MISMATCHED_REQUESTED_LINE",
                      audit([raw], now_utc=NOW)["rejection_counts"])
        raw = quote()
        raw["outcomes"][0]["unexpected"] = "sidecar"
        self.assertIn("INVALID_OUTCOME",
                      audit([raw], now_utc=NOW)["rejection_counts"])

    def test_malformed_rows_fail_closed_including_unhashable_payload(self):
        rows = [None, {"case_id": []}, {"case_id": {}},
                {"case_id": FEY, "bookmaker_id": []}, "unexpected"]
        result = audit(rows, now_utc=NOW)
        self.assertEqual(result["structurally_valid_pairs"], 0)
        self.assertEqual(sum(result["rejection_counts"].values()), len(rows))
        self.assertEqual(result["bets_authorized"], 0)

    def test_oversize_or_wrong_batch_cannot_create_coverage(self):
        result = audit([quote()] * 101, now_utc=NOW)
        self.assertIn("INVALID_OR_OVERSIZE_BATCH", result["rejection_counts"])
        self.assertEqual(result["structurally_valid_pairs"], 0)
        result = audit({"not": "a list"}, now_utc=NOW)
        self.assertEqual(result["status"], "HOLD")

    def test_no_source_metadata_or_self_claimed_independent_verification(self):
        raw = quote()
        raw.pop("provider_event_id")
        self.assertIn("INVALID_ROW_SHAPE",
                      audit([raw], now_utc=NOW)["rejection_counts"])
        raw = quote()
        raw["verified"] = True
        self.assertIn("INVALID_ROW_SHAPE",
                      audit([raw], now_utc=NOW)["rejection_counts"])

if __name__ == "__main__":
    unittest.main()
