"""Static worldwide league search is available, and HTML is escaped."""
import json
from datetime import datetime, timedelta, timezone
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_league_widget import inject


class GlobalLeagueWidgetTests(unittest.TestCase):
    def test_worldwide_search_escapes_provider_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "index.html").write_text(
                "<html><body><h2>近期賽程與賽果</h2></body></html>", encoding="utf-8")
            doc = {
                "schema": "football-king-global-league-catalog-v1",
                "production_recommendations": "DISABLED",
                "executable_odds_confirmed": False,
                "all_world_leagues_complete": False,
                "leagues_with_shadow": 1,
                "cards": [
                    {"id": "japan_j1", "name": "日本J1",
                     "coverage_state": "UNCALIBRATED_SHADOW",
                     "shadow_predictions": 2},
                    {"id": "no_more", "name": "<img src=x onerror=alert(1)>",
                     "coverage_state": "DISCOVERED_UNVERIFIED",
                     "shadow_predictions": 0},
                ],
            }
            (site / "global_league_catalog.json").write_text(
                json.dumps(doc), encoding="utf-8")
            (site / "worldwide_source_status.json").write_text(json.dumps({
                "schema": "football-king-worldwide-source-build-status-v1",
                "production_recommendations": "DISABLED",
                "status": "RESEARCH_ONLY",
                "requested_leagues": 8, "historical_games": 355,
                "two_source_schedule_agreements": 0,
            }), encoding="utf-8")
            result = inject(site)
            html = (site / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result["catalogue_rows"], 2)
            self.assertIn('id="fk-world-search"', html)
            self.assertIn("日本J1", html)
            self.assertNotIn("<img src=x", html)
            self.assertIn("&lt;img", html)
            self.assertIn("未通過核實", html)
            self.assertIn('id="fk-world-provenance"', html)
            self.assertIn("讀取歷史賽果 355 場", html)
            self.assertIn("時間一致 0 場", html)
            self.assertIn("worldwide_source_status.json", html)
            self.assertTrue((site / "global_league_catalog.js").is_file())
            self.assertTrue((site / "global_league_catalog.css").is_file())
            with self.assertRaisesRegex(ValueError, "DUPLICATE"):
                inject(site)

    def test_upcoming_worldwide_shadow_direction_is_visible_without_betting_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "index.html").write_text(
                "<html><body><h2>近期賽程與賽果</h2></body></html>", encoding="utf-8")
            now = datetime.now(timezone.utc)
            (site / "worldwide_shadow.json").write_text(json.dumps({
                "schema": "football-king-worldwide-uncalibrated-shadow-v1",
                "status": "SHADOW_ONLY", "as_of_utc": now.isoformat(),
                "production_recommendations": "DISABLED",
                "model_calibrated": False, "market_odds_available": False,
                "positive_ev_verified": False,
                "predictions": [{
                    "league": "germany_liga3", "home": "Home <script>",
                    "away": "Visitors", "kickoff_utc": (now + timedelta(hours=5)).isoformat(),
                    "prediction_utc": now.isoformat(),
                    "p_home": .54, "p_draw": .20, "p_away": .26,
                    "calibrated": False, "verified_market_odds": False,
                    "worldwide_two_distinct_schedule_feeds": True,
                    "production_recommendations": "DISABLED",
                }],
            }), encoding="utf-8")
            result = inject(site)
            page = (site / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result["upcoming_worldwide_shadow_cases"], 1)
            self.assertIn('id="fk-worldwide-forecast"', page)
            self.assertIn("54.0%", page)
            self.assertIn("冇可成交賠率", page)
            self.assertIn("Home &lt;script&gt;", page)
            self.assertNotIn("Home <script>", page)

    def test_expired_or_unsafe_worldwide_shadow_is_not_recommended(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "index.html").write_text("<html><body></body></html>", encoding="utf-8")
            now = datetime.now(timezone.utc)
            (site / "worldwide_shadow.json").write_text(json.dumps({
                "schema": "football-king-worldwide-uncalibrated-shadow-v1",
                "status": "SHADOW_ONLY",
                "as_of_utc": (now - timedelta(hours=12)).isoformat(),
                "production_recommendations": "DISABLED",
                "model_calibrated": False, "market_odds_available": False,
                "positive_ev_verified": False,
                "predictions": [{
                    "league": "germany_liga3", "home": "A", "away": "B",
                    "kickoff_utc": (now + timedelta(hours=3)).isoformat(),
                    "prediction_utc": now.isoformat(),
                    "p_home": 0.9, "p_draw": 0.05, "p_away": 0.05,
                    "calibrated": False, "verified_market_odds": False,
                    "worldwide_two_distinct_schedule_feeds": True,
                    "production_recommendations": "DISABLED",
                }],
            }), encoding="utf-8")
            result = inject(site)
            page = (site / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result["upcoming_worldwide_shadow_cases"], 0)
            self.assertIn("保持 HOLD", page)

    def test_missing_catalog_show_safe_empty_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "index.html").write_text(
                "<html><body></body></html>", encoding="utf-8")
            result = inject(site)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["catalogue_rows"], 0)
            self.assertEqual(result["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
