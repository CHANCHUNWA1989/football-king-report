"""iPhone dashboard is accessible, data-driven and excludes API secrets."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mobile_dashboard import inject,JS,CSS


class MobileDashboardTests(unittest.TestCase):
    def test_static_site_controls_and_no_dynamic_html_injection(self):
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)
            (site/"index.html").write_text("<html><body><h2>近期賽程與賽果</h2></body></html>",encoding="utf-8")
            result=inject(site)
            self.assertTrue(result["dashboard_visible"])
            doc=(site/"index.html").read_text(encoding="utf-8")
            self.assertIn('id="fk-hub"',doc)
            self.assertIn('id="fk-league"',doc)
            self.assertIn('id="fk-search"',doc)
            self.assertIn("正式投注建議：HOLD",doc)
            js=(site/"research_hub.js").read_text(encoding="utf-8")
            self.assertIn("textContent",js)
            self.assertNotIn("innerHTML",js)
            self.assertNotIn("THE_ODDS_API_KEY",js)
            self.assertNotIn("api.the-odds-api.com",js)
            self.assertIn("@media", (site/"research_hub.css").read_text(encoding="utf-8"))

    def test_duplicate_hub_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)
            (site/"index.html").write_text('<html><body><div id="fk-hub"></div></body></html>',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"DUPLICATE_RESEARCH_HUB"):
                inject(site)

    def test_missing_html_body_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)
            (site/"index.html").write_text("<p>no body")
            with self.assertRaisesRegex(ValueError,"HTML_BODY_REQUIRED"):
                inject(site)


if __name__=="__main__":
    unittest.main()
