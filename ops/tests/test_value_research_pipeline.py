import unittest
from value_research_pipeline import evaluate

class ValueResearchTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(evaluate([])["candidate_count"],0)
    def test_missing_evidence(self):
        report=evaluate([{"fixture_id":"1","market":"over_2_5"}])
        self.assertEqual(report["candidate_count"],0)
    def test_negative_ev(self):
        report=evaluate([{"odds":1.3,"probability":0.75,"calibrated":True,"fresh_odds":True}])
        self.assertEqual(report["candidate_count"],0)
    def test_unverified_model(self):
        report=evaluate([{"odds":2.1,"probability":0.6,"fresh_odds":True}])
        self.assertEqual(report["candidate_count"],0)
    def test_positive_candidate_not_production(self):
        report=evaluate([{"odds":2.1,"probability":0.55,"calibrated":True,"fresh_odds":True}])
        self.assertEqual(report["candidate_count"],1)
        self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_asian_spread_binary_flags_cannot_create_false_candidate(self):
        for market in ("asian_handicap", "Asian Handicap", "spreads", "AH", "asian-spread"):
            with self.subTest(market=market):
                report = evaluate([{
                    "fixture_id": "troyes-le-havre-20261120",
                    "market": market, "selection": "HOME", "side": "HOME",
                    "line": -.25, "odds": 1.943, "probability": .90,
                    "calibrated": True, "fresh_odds": True,
                    "quote_executable_verified": True,
                    "ready_for_production": True,
                }])
                self.assertEqual(report["candidate_count"], 0)
                one = report["results"][0]
                self.assertFalse(one["research_candidate"])
                self.assertIn("asian_research_scenario", one)
                self.assertFalse(one["asian_research_scenario"]["positive_expected_value_verified"])
                self.assertEqual(one["production_recommendations"], "DISABLED")
                self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_asian_quarter_ev_reports_exact_algebra_only(self):
        report = evaluate([{
            "fixture_id": "example-unsealed", "market": "asian_handicap",
            "side": "HOME", "selection": "HOME", "line": -.25,
            "odds": 1.943, "threeway_probabilities": [.45, .285, .265],
            "probability": .9, "calibrated": True, "fresh_odds": True
        }])
        self.assertEqual(report["candidate_count"], 0)
        scenario = report["results"][0]["asian_research_scenario"]
        self.assertAlmostEqual(scenario["nominal_ev_per_unit_claimed_price"],
                               .45 * 1.943 + .285 * .5 - 1, places=7)
        self.assertFalse(scenario["positive_expected_value_verified"])
        self.assertEqual(scenario["reason"], "NO_CONSERVATIVE_PROBABILITY_BOUNDS")

    def test_valid_math_claim_still_not_a_qualified_recommendation(self):
        row = evaluate([{
            "market": "spreads", "selection": "HOME", "side": "HOME",
            "line": -.25, "odds": 1.90,
            "threeway_probabilities": [.7, .2, .1],
            "conservative_threeway_lower_bounds": [.65, .15, .05],
            "quote_age_seconds": 20,
            "calibrated": True, "fresh_odds": True
        }])["results"][0]
        self.assertTrue(row["asian_research_scenario"]["research_value_screen_pass"])
        self.assertEqual(row["blockers"], ["ASIAN_MATH_ONLY_NOT_INDEPENDENTLY_CERTIFIED"])
        self.assertFalse(row["research_candidate"])
        self.assertEqual(row["asian_research_scenario"]["formal_bet_count"], 0)

    def test_wide_asian_line_1x2_refused(self):
        row = evaluate([{
            "market": "asian_handicap", "side": "HOME", "line": -.75,
            "odds": 2.0, "probability": .99,
            "threeway_probabilities": [.8, .1, .1],
            "calibrated": True, "fresh_odds": True,
        }])["results"][0]
        self.assertEqual(row["blockers"], ["NEEDS_FULL_SCORE_MARGIN_DISTRIBUTION"])
        self.assertFalse(row["research_candidate"])

    def test_binary_legacy_path_stays_research_only(self):
        row = evaluate([{"market": "1x2", "odds": 2.1,
                         "probability": 0.55, "calibrated": True,
                         "fresh_odds": True}])["results"][0]
        self.assertTrue(row["research_candidate"])
        self.assertEqual(row["production_recommendations"], "DISABLED")


    def test_totals_aliases_never_use_binary_ev_shortcut(self):
        for market, side in (
            ("over_2_5", "OVER"), ("under_2_75", "UNDER"),
            ("totals", "OVER"), ("asian_totals", "OVER"),
            ("o/u_2.75", "OVER"), ("goals_over_2_75", "OVER"),
            ("over2.75", "OVER"), ("under2.75", "UNDER"),
        ):
            with self.subTest(market=market):
                expected_line = 2.5 if market == "over_2_5" else 2.75
                result = evaluate([{
                    "market": market, "selection": side, "side": side,
                    "line": expected_line, "odds": 2.0, "probability": .95,
                    "calibrated": True, "fresh_odds": True,
                    "verified": True, "quote_executable_verified": True,
                }])
                self.assertEqual(result["candidate_count"], 0)
                row = result["results"][0]
                self.assertFalse(row["research_candidate"])
                self.assertEqual(row["blockers"], ["NEEDS_FULL_TOTAL_GOAL_DISTRIBUTION"])
                self.assertEqual(row["production_recommendations"], "DISABLED")

    def test_quarter_totals_exact_half_loss_prevents_false_positive(self):
        result = evaluate([{
            "fixture_id": "synthetic-total", "market": "over_2_75",
            "selection": "OVER", "side": "OVER", "line": 2.75,
            "odds": 2.0, "probability": .6,
            "goal_total_probabilities": {"2": .4, "3": .6},
            "calibrated": True, "fresh_odds": True,
        }])
        row = result["results"][0]
        self.assertEqual(result["candidate_count"], 0)
        self.assertFalse(row["research_candidate"])
        self.assertAlmostEqual(
            row["total_goals_research_scenario"]["nominal_ev_per_unit_claimed_price"],
            -.1, places=6)
        self.assertFalse(row["total_goals_research_scenario"]["positive_expected_value_verified"])

    def test_totals_exact_math_pass_never_produces_recommendation(self):
        result = evaluate([{
            "market": "totals", "selection": "OVER", "line": 2.75,
            "odds": 2.0, "goal_total_probabilities": {"2": .2, "3": .8},
            "conservative_goal_total_lower_bounds": {"2": .1, "3": .72},
            "quote_age_seconds": 20,
            "calibrated": True, "fresh_odds": True,
            "quote_executable_verified": True
        }])
        row = result["results"][0]
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(row["blockers"], ["TOTAL_MATH_ONLY_NOT_INDEPENDENTLY_CERTIFIED"])
        self.assertTrue(row["total_goals_research_scenario"]["research_value_screen_pass"])
        self.assertFalse(row["total_goals_research_scenario"]["positive_expected_value_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_totals_market_direction_conflicts_and_missing_side_hold(self):
        for market, side, selection in (
            ("over_2_75", None, "UNDER"),
            ("over2.75", "UNDER", None),
            ("under_2_75", "OVER", "OVER"),
            ("totals", None, None),
            ("totals", "OVER", "UNDER"),
            ("totals", "HOME", None),
        ):
            with self.subTest(market=market, side=side, selection=selection):
                row = evaluate([{
                    "market": market, "selection": selection, "side": side,
                    "line": 2.75, "odds": 2.0, "probability": .9,
                    "goal_total_probabilities": {"2": .2, "3": .8},
                    "fresh_odds": True, "calibrated": True,
                }])["results"][0]
                self.assertFalse(row["research_candidate"])
                self.assertEqual(row["blockers"], ["TOTAL_MARKET_SELECTION_CONFLICT_OR_MISSING"])

    def test_market_encoded_total_line_must_match_payload_line(self):
        for market, line, selection in (
            ("over_2_5", 2.75, "OVER"),
            ("under_2_75", 2.5, "UNDER"),
            ("over2.75", 2.5, "OVER"),
            ("under2.75", 2.5, "UNDER"),
            ("o/u_2.5", 2.75, "OVER"),
        ):
            with self.subTest(market=market, line=line):
                row = evaluate([{
                    "market": market, "selection": selection, "line": line,
                    "odds": 2.0, "probability": .95,
                    "goal_total_probabilities": {"2": .4, "3": .6},
                    "calibrated": True, "fresh_odds": True,
                }])["results"][0]
                self.assertFalse(row["research_candidate"])
                self.assertEqual(row["blockers"], ["TOTAL_MARKET_LINE_MISMATCH"])


    def test_over_25_missing_line_cannot_pass_even_with_scalar_probability(self):
        row = evaluate([{
            "market": "over_2_5", "selection": "OVER", "odds": 3,
            "probability": .9, "goal_total_probabilities": {"3": 1},
            "calibrated": True, "fresh_odds": True,
        }])["results"][0]
        self.assertFalse(row["research_candidate"])
        self.assertEqual(row["total_goals_research_scenario"]["reason"], "INVALID_TOTAL_LINE")


if __name__=="__main__":
    unittest.main()
