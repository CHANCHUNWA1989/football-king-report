"""On-demand Safari German source panel must not render stale unverified live scores."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from german_live_widget import inject


class GermanWidgetTests(unittest.TestCase):
    def test_widget_has_attribution_and_one_click_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"index.html").write_text("<html><body><div id='fk-hub'></div></body></html>")
            out=inject(p)
            self.assertEqual(out["odds_calls"],0)
            h=(p/"index.html").read_text(encoding="utf-8")
            js=(p/"german_live.js").read_text(encoding="utf-8")
            self.assertIn('id="fk-german-live"',h)
            self.assertIn('id="gl-refresh"',h)
            self.assertIn("https://www.openligadb.de/lizenz",h)
            self.assertIn("live_germany_latest.json",js)
            self.assertIn("textContent",js)
            self.assertNotIn("innerHTML",js)
            self.assertIn("150*60*1000",js)
            self.assertIn("document.addEventListener('visibilitychange'",js)
            self.assertIn("KICKOFF_CONFLICT_REVIEW",js)
            self.assertIn("HOLD",js)
            self.assertNotIn("THE_ODDS_API_KEY",js)
            self.assertNotIn("api.the-odds-api.com",js)

    def test_duplicate_widget_not_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"index.html").write_text('<html><body><div id="fk-german-live"></div></body></html>')
            with self.assertRaisesRegex(ValueError,"DUPLICATE_GERMAN_WIDGET"):
                inject(p)

    def test_no_html_body_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"index.html").write_text("<h1>no body")
            with self.assertRaisesRegex(ValueError,"INVALID_OR_DUPLICATE_GERMAN_WIDGET"):
                inject(p)


if __name__=="__main__":
    unittest.main()
