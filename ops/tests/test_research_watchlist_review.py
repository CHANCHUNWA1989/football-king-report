"""Synthetic regression: no cherry-picking winning research selections."""
import copy
import unittest
from ops.research_watchlist_review import review

CHECKED = "2026-11-07T06:00:00Z"
KICKOFF = "2026-11-06T20:00:00Z"


def choice(sid="a", *, market="h2h", side="home", line=0,
           odds="2.10", decision="PRIORITY_RESEARCH"):
    row = {
        "selection_id": sid, "fixture_id": "fixture-" + sid,
        "competition": "synthetic", "model_version": "shadow-1",
        "market": market, "selection": side, "line": line,
        "decimal_odds": odds, "decision": decision,
        "registered_at_utc": "2026-11-06T19:00:00Z",
        "kickoff_at_utc": KICKOFF,
    }
    if odds is not None:
        row.update(bookmaker="synthetic", quote_updated_at_utc="2026-11-06T18:50:00Z",
                   captured_at_utc="2026-11-06T18:55:00Z")
    return row


def final(sid="a", home=1, away=0):
    return {
        "fixture_id": "fixture-" + sid,
        "kickoff_at_utc": KICKOFF,
        "finished_at_utc": "2026-11-06T22:10:00Z",
        "home_goals": home, "away_goals": away,
        "source_independently_verified": True,
    }


class ResearchWatchlistReviewTests(unittest.TestCase):
    def test_complete_cohort_includes_losses_exclusions_and_hold(self):
        watch = [
            choice("a"),  # selected loses
            choice("b", market="asian_handicap", side="away", line="1.25",
                   odds="1.95", decision="WATCH"),  # half win
            choice("c", market="totals", side="under", line="2.5",
                   odds="1.70", decision="EXCLUDED"),  # would win, but not selected
            choice("d", market="totals", side="over", line="2.5",
                   odds=None, decision="HOLD"),
        ]
        outcomes = [final("a", 0, 1), final("b", 2, 1),
                    final("c", 0, 0), final("d", 1, 1)]
        original = copy.deepcopy(watch)
        report = review(watch, outcomes, checked_at_utc=CHECKED)
        self.assertEqual(watch, original)
        self.assertEqual(report["predeclared_count"], 4)
        self.assertEqual(report["distinct_fixtures"], 4)
        self.assertEqual(len(report["cases"]), 4)
        self.assertEqual(report["cases"][0]["settlement_grade_research_only"], "FULL_LOSS")
        self.assertAlmostEqual(report["cases"][0]["hypothetical_net_units"], -1)
        self.assertEqual(report["cases"][1]["settlement_grade_research_only"], "HALF_WIN")
        self.assertAlmostEqual(report["cases"][1]["hypothetical_net_units"], .475)
        self.assertEqual(report["cases"][2]["settlement_grade_research_only"], "FULL_WIN")
        self.assertAlmostEqual(report["cases"][2]["hypothetical_net_units"], .7)
        self.assertIsNone(report["cases"][3]["hypothetical_net_units"])
        self.assertEqual(report["by_decision"]["PRIORITY_RESEARCH"]["scored_research_only"], 1)
        self.assertEqual(report["by_decision"]["PRIORITY_RESEARCH"]["hypothetical_roi_settled_only"], -1)
        self.assertEqual(report["by_decision"]["EXCLUDED"]["scored_research_only"], 1)
        self.assertEqual(report["by_decision"]["HOLD"]["missing_usable_price"], 1)
        self.assertFalse(report["results_independently_verified"])
        self.assertFalse(report["prematch_manifest_independently_attested"])
        self.assertFalse(report["traded_prices_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_total_quarter_line_half_loss_and_push(self):
        over = choice("q", market="totals", side="over", line="3.25", odds="1.90")
        push = choice("p", market="totals", side="under", line="3.0", odds="1.90")
        result = review([over, push], [final("q", 2, 1), final("p", 2, 1)],
                        checked_at_utc=CHECKED)
        self.assertEqual([x["settlement_grade_research_only"] for x in result["cases"]],
                         ["HALF_LOSS", "PUSH"])
        self.assertEqual([x["hypothetical_net_units"] for x in result["cases"]], [-.5, 0.0])

    def test_missing_scores_retained_in_denominator(self):
        watch = [choice("a"), choice("b", decision="EXCLUDED")]
        report = review(watch, [final("a", 0, 1)], checked_at_utc=CHECKED)
        self.assertEqual(report["predeclared_count"], 2)
        self.assertEqual(report["by_decision"]["EXCLUDED"]["all_predeclared"], 1)
        self.assertEqual(report["by_decision"]["EXCLUDED"]["pending_or_unverifiable"], 1)
        self.assertIsNone(report["by_decision"]["EXCLUDED"]["hypothetical_roi_settled_only"])
        self.assertEqual(report["cases"][1]["result_status"], "NO_RESULT")

    def test_duplicate_result_quarantines_all_scores_for_fixture(self):
        q = choice("a")
        report = review([q], [final("a", 1, 0), final("a", 0, 1)],
                        checked_at_utc=CHECKED)
        self.assertEqual(report["cases"][0]["result_status"], "AMBIGUOUS_DUPLICATE_RESULT")
        self.assertIsNone(report["cases"][0]["hypothetical_net_units"])
        self.assertEqual(report["status"], "HOLD")

    def test_duplicate_market_identity_even_different_price_rejected(self):
        a = choice("a")
        b = choice("b", odds="3.10", decision="EXCLUDED")
        b["fixture_id"] = a["fixture_id"]
        with self.assertRaisesRegex(ValueError, "DUPLICATE_MARKET_DECISION"):
            review([a, b], [], checked_at_utc=CHECKED)

    def test_duplicate_selection_id_and_posthoc_timestamps_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SELECTION_ID"):
            review([choice("a"), choice("a")], [], checked_at_utc=CHECKED)
        for registration in ("2026-11-06T20:00:00Z", "2026-11-06T22:00:00Z",
                             "2026-11-07T06:01:00Z"):
            with self.subTest(registration=registration):
                a = choice("a")
                a["registered_at_utc"] = registration
                with self.assertRaises(ValueError):
                    review([a], [], checked_at_utc=CHECKED)

    def test_invalid_quote_and_stale_clock_fail_closed(self):
        for key, value in [
            ("decimal_odds", True), ("decimal_odds", "nan"),
            ("quote_updated_at_utc", "2026-11-06T18:30:00Z"),
            ("captured_at_utc", "2026-11-06T18:49:00Z"),
            ("captured_at_utc", "2026-11-06T19:02:00Z"),
            ("registered_at_utc", "2026-11-06T19:30:00Z"),
        ]:
            with self.subTest(key=key, value=value):
                a = choice("a")
                a[key] = value
                with self.assertRaises(ValueError):
                    review([a], [], checked_at_utc=CHECKED)

    def test_market_identity_and_exact_line_enforced(self):
        for market, side, line in [
            ("asian_handicap", "draw", 1.25), ("totals", "away", 2.5),
            ("totals", "under", "-2.5"), ("totals", "over", "2.3"),
            ("h2h", "home", "1.0"), ("unknown", "home", 0),
        ]:
            with self.subTest(market=market, side=side, line=line):
                with self.assertRaises(ValueError):
                    review([choice("a", market=market, side=side, line=line)], [],
                           checked_at_utc=CHECKED)

    def test_invalid_and_wrong_kickoff_result_not_settled(self):
        wrong = final("a", 1, 0)
        wrong["kickoff_at_utc"] = "2026-11-06T21:00:00Z"
        other = final("b", 1, 0)
        other["finished_at_utc"] = "2026-11-08T00:00:00Z"
        result = review([choice("a"), choice("b")], [wrong, other],
                        checked_at_utc=CHECKED)
        self.assertTrue(all(x["result_status"] == "INVALID_FINAL_RESULT" for x in result["cases"]))
        self.assertTrue(all(x["hypothetical_net_units"] is None for x in result["cases"]))

    def test_self_declared_source_verified_never_becomes_real_roi(self):
        a = choice("a")
        a["prematch_capture_independently_attested"] = True
        result = review([a], [final("a", 1, 0)], checked_at_utc=CHECKED)
        self.assertFalse(result["prematch_manifest_independently_attested"])
        self.assertFalse(result["results_independently_verified"])
        self.assertFalse(result["hypothetical_returns_are_actual_bets"])
        self.assertFalse(result["model_improvement_verified"])
        self.assertEqual(result["cases"][0]["result_status"],
                         "OBSERVED_NOT_INDEPENDENTLY_VERIFIED")


if __name__ == "__main__":
    unittest.main()
