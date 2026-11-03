"""Regression checks for the UCL sidecar's fail-closed four-market scope."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ucl_four_market_shadow import analyze, hypothetical_distribution, settle

NOW = datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc)
ATM = "ucl26m4-atletico-bayern"
FEY = "ucl26m4-feyenoord-inter"
BAR = "ucl26m4-barcelona-villa"
PSG = "ucl26m4-villarreal-psg"


def structurally_fresh_quote():
    return {
        "fixture_id": ATM, "market_id": "asian_handicap",
        "selection": "HOME", "line": 0.25,
        "decimal_odds": 1.91, "source": "PRIVATE_TEST_SOURCE",
        "bookmaker_id": "PRIVATE_TEST_BOOK",
        "provider_fixture_id": "TEST_PROVIDER_MATCH_123",
        "observed_at_utc": "2026-11-03T18:59:45Z",
        "captured_at_utc": "2026-11-03T18:59:55Z",
    }


class UclFourMarketTests(unittest.TestCase):
    def test_default_four_fixtures_are_hold_with_no_made_up_prices(self):
        out = analyze(now_utc=NOW)
        self.assertEqual(out["fixture_count"], 4)
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["production_recommendations"], "DISABLED")
        self.assertEqual(out["bets_authorized"], 0)
        self.assertFalse(out["positive_expected_value_verified"])
        self.assertEqual([r["market"] for r in out["cases"]], [
            "asian_handicap", "corners_total", "first_half_goals", "asian_handicap"])
        self.assertTrue(all(r["quote_status"] == "MISSING_QUOTE"
                            and r["model_status"] == "MISSING_DISTRIBUTION"
                            and r["provider_native_fixture_id"] is None
                            for r in out["cases"]))

    def test_user_requested_handicap_quarter_grades(self):
        self.assertEqual(settle(ATM, home_goals=0, away_goals=0), "HALF_WIN")
        self.assertEqual(settle(ATM, home_goals=1, away_goals=0), "FULL_WIN")
        self.assertEqual(settle(ATM, home_goals=0, away_goals=1), "FULL_LOSS")
        self.assertEqual(settle(PSG, home_goals=0, away_goals=1), "HALF_WIN")
        self.assertEqual(settle(PSG, home_goals=0, away_goals=2), "FULL_WIN")
        self.assertEqual(settle(PSG, home_goals=0, away_goals=0), "FULL_LOSS")

    def test_corners_and_first_half_totals_have_distinct_grading(self):
        self.assertEqual(settle(FEY, count=9), "PUSH")
        self.assertEqual(settle(FEY, count=10), "FULL_WIN")
        self.assertEqual(settle(FEY, count=8), "FULL_LOSS")
        self.assertEqual(settle(BAR, count=2), "HALF_WIN")
        self.assertEqual(settle(BAR, count=3), "FULL_WIN")
        self.assertEqual(settle(BAR, count=1), "FULL_LOSS")

    def test_reject_invalid_scores_and_market_mixing(self):
        for case, kwargs in (
            (ATM, {"count": 9}),
            (FEY, {"home_goals": 1, "away_goals": 0}),
            (BAR, {"count": True}),
            (PSG, {"home_goals": -1, "away_goals": 2}),
        ):
            with self.subTest(case=case), self.assertRaises(ValueError):
                settle(case, **kwargs)

    def test_assumed_distribution_is_not_certified(self):
        grades = hypothetical_distribution(FEY, {"9": 0.2, "10": 0.8})
        self.assertEqual(grades["PUSH"], 0.2)
        self.assertEqual(grades["FULL_WIN"], 0.8)
        result = analyze(now_utc=NOW, distributions={FEY: {"9": 0.2, "10": 0.8}})
        row = next(r for r in result["cases"] if r["case_id"] == FEY)
        self.assertEqual(row["model_status"], "UNVERIFIED_ASSUMPTION_ONLY")
        self.assertFalse(row["model_distribution_calibrated"])
        self.assertEqual(row["status"], "HOLD")
        self.assertFalse(result["positive_expected_value_verified"])

    def test_non_normalized_and_noncanonical_distributions_rejected(self):
        for dist in ({"9": 0.1, "10": 0.1}, {"09": 1.0},
                     {"-1": 1.0}, {"9": True}, {"9": float("nan")}):
            with self.subTest(dist=dist), self.assertRaises(ValueError):
                hypothetical_distribution(FEY, dist)
        report = analyze(now_utc=NOW, distributions={FEY: {"9": 0.6}})
        row = next(r for r in report["cases"] if r["case_id"] == FEY)
        self.assertEqual(row["model_status"], "INVALID_ASSUMPTION_DISTRIBUTION")
        self.assertIsNone(row["hypothetical_five_grade_probabilities"])

    def test_fresh_quote_still_does_not_authorize_bets_or_publish_private_details(self):
        quote = structurally_fresh_quote()
        result = analyze(now_utc=NOW, quotes={ATM: quote})
        row = result["cases"][0]
        self.assertEqual(row["quote_status"],
                         "STRUCTURAL_ONLY_SOURCE_UNAUTHENTICATED")
        self.assertFalse(row["market_price_authenticated"])
        self.assertEqual(result["bets_authorized"], 0)
        public_text = json.dumps(result)
        for forbidden in ("PRIVATE_TEST_BOOK", "TEST_PROVIDER_MATCH_123",
                          "PRIVATE_TEST_SOURCE", "1.91"):
            self.assertNotIn(forbidden, public_text)

    def test_wrong_fixture_line_or_stale_quote_stays_hold(self):
        quote = structurally_fresh_quote()
        quote["line"] = -0.25
        row = analyze(now_utc=NOW, quotes={ATM: quote})["cases"][0]
        self.assertEqual(row["quote_status"], "QUOTE_FIXTURE_MARKET_LINE_MISMATCH")
        quote = structurally_fresh_quote()
        quote["observed_at_utc"] = "2026-11-03T18:39:45Z"
        quote["captured_at_utc"] = "2026-11-03T18:40:00Z"
        row = analyze(now_utc=NOW, quotes={ATM: quote})["cases"][0]
        self.assertEqual(row["quote_status"], "STALE_CAPTURE")
        quote = structurally_fresh_quote()
        quote["observed_at_utc"] = "2026-11-03T18:56:00Z"
        row = analyze(now_utc=NOW, quotes={ATM: quote})["cases"][0]
        self.assertEqual(row["quote_status"], "STALE_MARKET_UPDATE")
        quote = structurally_fresh_quote()
        quote["observed_at_utc"] = "2026-11-03T19:00:10Z"
        row = analyze(now_utc=NOW, quotes={ATM: quote})["cases"][0]
        self.assertEqual(row["quote_status"], "QUOTE_CHRONOLOGY_MISMATCH")

    def test_post_kickoff_cannot_be_prematch_quote(self):
        quote = structurally_fresh_quote()
        t = datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc)
        row = analyze(now_utc=t, quotes={ATM: quote})["cases"][0]
        self.assertEqual(row["quote_status"], "QUOTE_CHRONOLOGY_MISMATCH")

    def _complete_corners_block(self):
        return {
            "case_id": FEY,
            "fixture": {"home": "Feyenoord", "away": "Inter",
                        "kickoff_utc": "2026-11-03T20:00:00+00:00"},
            "provider": "PRIVATE_TEST_SOURCE",
            "provider_event_id": "PRIVATE_NATIVE_EVENT_X",
            "bookmaker_id": "PRIVATE_TEST_BOOK",
            "market_id": "corners_total",
            "market_updated_utc": "2026-11-03T18:59:40Z",
            "captured_utc": "2026-11-03T18:59:48Z",
            "outcomes": [
                {"selection": "OVER", "line": 9.0, "decimal_odds": 1.98},
                {"selection": "UNDER", "line": 9.0, "decimal_odds": 1.88},
            ],
        }

    def test_special_market_single_quote_cannot_bypass_atomic_gate(self):
        quote = structurally_fresh_quote()
        quote.update({"fixture_id": FEY, "market_id": "corners_total",
                      "selection": "OVER", "line": 9.0})
        result = analyze(now_utc=NOW, quotes={FEY: quote})
        row = next(x for x in result["cases"] if x["case_id"] == FEY)
        self.assertEqual(row["quote_status"], "SPECIAL_REQUIRES_ATOMIC_PAIR")
        self.assertEqual(result["special_market_atomic_pairs"], 0)
        self.assertFalse(row["market_price_authenticated"])

    def test_structural_pair_flows_into_four_case_report_but_remains_hold(self):
        block = self._complete_corners_block()
        result = analyze(now_utc=NOW, special_market_blocks=[block])
        row = next(x for x in result["cases"] if x["case_id"] == FEY)
        other = next(x for x in result["cases"] if x["case_id"] == BAR)
        self.assertEqual(row["quote_status"],
                         "SPECIAL_ATOMIC_PAIR_SOURCE_UNAUTHENTICATED")
        self.assertEqual(other["quote_status"], "MISSING_ATOMIC_PAIR")
        self.assertEqual(result["special_market_atomic_pairs"], 1)
        self.assertEqual(result["bets_authorized"], 0)
        self.assertEqual(result["status"], "HOLD")
        self.assertFalse(result["independently_authenticated_odds"])
        serialized = json.dumps(result)
        for secret in ("PRIVATE_TEST_SOURCE", "PRIVATE_TEST_BOOK",
                       "PRIVATE_NATIVE_EVENT_X", "1.98", "1.88"):
            self.assertNotIn(secret, serialized)

    def test_incomplete_or_post_kickoff_special_pair_stays_missing(self):
        incomplete = self._complete_corners_block()
        incomplete["outcomes"] = incomplete["outcomes"][:1]
        row = next(x for x in analyze(
            now_utc=NOW, special_market_blocks=[incomplete])["cases"]
                   if x["case_id"] == FEY)
        self.assertEqual(row["quote_status"], "MISSING_ATOMIC_PAIR")
        too_late = datetime(2026, 11, 3, 20, 1, tzinfo=timezone.utc)
        row = next(x for x in analyze(
            now_utc=too_late, special_market_blocks=[
                self._complete_corners_block()])["cases"]
                   if x["case_id"] == FEY)
        self.assertEqual(row["quote_status"], "MISSING_ATOMIC_PAIR")

    def test_unknown_case_cannot_fuzz_match_identity(self):
        with self.assertRaisesRegex(ValueError, "INVALID_UCL_INPUT_SCOPE"):
            analyze(now_utc=NOW, quotes={"ucl-synthetic-extra": {}})
        with self.assertRaisesRegex(ValueError, "INVALID_UCL_INPUT_SCOPE"):
            analyze(now_utc=NOW, distributions={"ucl-synthetic-extra": {"1": 1.0}})
        with self.assertRaisesRegex(ValueError, "UNKNOWN_UCL_CASE"):
            settle("ucl-synthetic-extra", count=8)


if __name__ == "__main__":
    unittest.main()
