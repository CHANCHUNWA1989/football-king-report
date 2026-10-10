"""Static worldwide league search is available, and HTML is escaped."""
import json
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
            result = inject(site)
            html = (site / "index.html").read_text(encoding="utf-8")
            self.assertEqual(result["catalogue_rows"], 2)
            self.assertIn('id="fk-world-search"', html)
            self.assertIn("日本J1", html)
            self.assertNotIn("<img src=x", html)
            self.assertIn("&lt;img", html)
            self.assertIn("未通過核實", html)
            self.assertTrue((site / "global_league_catalog.js").is_file())
            self.assertTrue((site / "global_league_catalog.css").is_file())
            with self.assertRaisesRegex(ValueError, "DUPLICATE"):
                inject(site)

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
