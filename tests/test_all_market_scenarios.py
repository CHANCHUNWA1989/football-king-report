import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ops.all_market_scenarios import total_scenario, ah_scenario, build, publish

NOW = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)

def shadow():
    return {
        "schema": "football-king-uncalibrated-shadow-1",
        "status": "SHADOW_ONLY", "model_calibrated": False,
        "production_recommendations": "DISABLED", "as_of_utc": NOW.isoformat(),
        "predictions": [{
            "league": "epl", "home": "Arsenal", "away": "Everton",
            "kickoff_utc": (NOW+timedelta(days=1)).isoformat(),
            "prediction_utc": NOW.isoformat(),
            "expected_home_goals": 1.75, "expected_away_goals": 0.85,
            "calibrated": False, "production_recommendations": "DISABLED",
        }]}

class AllMarketResearchTests(unittest.TestCase):
    def test_totals_half_win_settlement(self):
        over = total_scenario(1.4, 1.3, side="OVER", line=2.75)
        under = total_scenario(1.4, 1.3, side="UNDER", line=2.75)
        self.assertGreater(over["settlement_probabilities"]["HALF_WIN"], 0.01)
        self.assertGreater(under["settlement_probabilities"]["HALF_LOSS"], 0.01)
        self.assertAlmostEqual(sum(over["settlement_probabilities"].values()), 1, places=6)
        self.assertAlmostEqual(sum(under["settlement_probabilities"].values()), 1, places=6)
        self.assertFalse(over["positive_expected_value_verified"])
        self.assertFalse(under["actual_bookmaker_quote_available"])

    def test_no_push_at_two_point_five(self):
        over = total_scenario(1.4, 1.3, side="OVER", line=2.5)
        under = total_scenario(1.4, 1.3, side="UNDER", line=2.5)
        self.assertAlmostEqual(over["settlement_probabilities"]["PUSH"], 0, places=6)
        self.assertAlmostEqual(
            over["settlement_probabilities"]["FULL_WIN"] +
            under["settlement_probabilities"]["FULL_WIN"], 1, places=6)

    def test_asian_home_and_away_quarter_line(self):
        h = ah_scenario(1.8, 1.0, "HOME", -0.25)
        a = ah_scenario(1.8, 1.0, "AWAY", +0.25)
        self.assertGreater(h["settlement_probabilities"]["HALF_LOSS"], 0)
        self.assertGreater(a["settlement_probabilities"]["HALF_WIN"], 0)
        self.assertFalse(h["actual_bookmaker_quote_available"])
        self.assertFalse(a["positive_expected_value_verified"])

    def test_model_all_markets_has_no_bets_or_laundered_quote(self):
        report = build(shadow(), NOW)
        self.assertEqual(report["status"], "RESEARCH_ONLY")
        self.assertEqual(len(report["matches"]), 1)
        self.assertEqual(len(report["matches"][0]["scenarios"]), 4)
        self.assertEqual(report["recommended_bets"], [])
        self.assertFalse(report["market_quotes_observed"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        serialized=json.dumps(report)
        self.assertNotIn("VERIFIED_VALUE",serialized)
        self.assertNotIn("betting_odds",serialized)

    def test_stale_model_and_future_prices_rejected(self):
        self.assertEqual(build(shadow(), NOW+timedelta(days=2))["status"], "HOLD")
        expired=shadow()
        expired["as_of_utc"]=(NOW-timedelta(days=1)).isoformat()
        self.assertEqual(build(expired, NOW)["status"], "HOLD")
        expired=shadow()
        expired["production_recommendations"]="ENABLED"
        self.assertEqual(build(expired,NOW)["status"], "HOLD")

    def test_duplicate_and_postkickoff_fixtures_excluded(self):
        data=shadow()
        data["predictions"].append(dict(data["predictions"][0]))
        self.assertEqual(len(build(data,NOW)["matches"]),1)
        data["predictions"][0]["kickoff_utc"]=(NOW-timedelta(hours=1)).isoformat()
        self.assertEqual(len(build(data,NOW)["matches"]),1)

    def test_site_integrates_safe_json_and_escaped_teams(self):
        data=shadow()
        data["predictions"][0]["home"]="<script>alert('x')</script>"
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/"index.html").write_text("<html><main><h2>近期賽程與賽果</h2></main></html>",encoding="utf-8")
            (p/"shadow.json").write_text(json.dumps(data),encoding="utf-8")
            report=publish(p,NOW)
            html=(p/"index.html").read_text(encoding="utf-8")
            self.assertIn('id="fk-all-market-hypotheses"',html)
            self.assertNotIn("<script>",html)
            self.assertEqual(report["production_recommendations"],"DISABLED")
            self.assertEqual(json.loads((p/"all_market_scenarios.json").read_text())["status"],
                             "RESEARCH_ONLY")
            with self.assertRaisesRegex(ValueError,"DUPLICATE_MARKET_HYPOTHESIS"):
                publish(p,NOW)

if __name__=="__main__":
    unittest.main()
