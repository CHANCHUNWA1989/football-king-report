import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from ops.public_readiness_site import build, publish, render_section

NOW = datetime(2026, 10, 10, 11, tzinfo=timezone.utc)
SETTLED = {"samples": [{"key": "match1", "league": "bundesliga",
                         "kickoff_utc": "2026-10-09T19:00:00+00:00",
                         "fixture_result_source_independently_verified": False}],
           "n": 1, "production_recommendations": "DISABLED"}
GATES = {"captured_utc": "2026-10-10T08:46:54+00:00",
         "checks": [
             {"key": "model_promotion_safety", "state": "PASS"},
             {"key": "out_of_sample_calibration", "state": "HOLD"},
             {"key": "utc_fixture_identity", "state": "PARTIAL"}]}
MARKET = {"as_of_utc": "2026-10-10T01:21:15+00:00",
          "status": "RESEARCH_ONLY", "event_count": 117}

class PublicReadinessTests(unittest.TestCase):
    def test_real_evidence_shows_gap_not_fake_completion(self):
        result = build(SETTLED, GATES, MARKET, NOW)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["quality_gates_passed"], 1)
        self.assertEqual(result["recorded_settled_cases"], 1)
        self.assertEqual(result["result_rows_marked_independently_verified"], 0)
        self.assertEqual(result["still_needed_if_existing_rows_pass_independent_audit"], 300)
        self.assertFalse(result["actual_bettable_odds_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("decimal_odds", json.dumps(result))

    def test_rejects_stale_market_and_quality(self):
        result = build(SETTLED, GATES, MARKET,
                       datetime(2026, 11, 10, tzinfo=timezone.utc))
        self.assertFalse(result["market_baseline_fresh"])
        self.assertFalse(result["quality_fresh"])
        self.assertEqual(result["market_baseline_event_count"], 0)

    def test_no_untrusted_html_or_raw_quotes(self):
        progress = build(SETTLED, GATES, MARKET, NOW)
        markup = render_section(progress)
        self.assertIn('id="fk-official-readiness"', markup)
        self.assertIn("HOLD", markup)
        self.assertNotIn("bookmaker", markup)
        self.assertNotIn("3.75", markup)

    def test_end_to_end_publication_without_raw_data(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            site = p / "site"
            site.mkdir()
            (site / "index.html").write_text(
                "<html><main><h2>近期賽程與賽果</h2></main></html>",
                encoding="utf-8")
            for n, payload in (("settled.json", SETTLED),
                               ("gates.json", GATES), ("market.json", MARKET)):
                (p / n).write_text(json.dumps(payload), encoding="utf-8")
            report = publish(site, p / "settled.json", p / "gates.json",
                             p / "market.json", now=NOW)
            result = json.loads((site / "official_readiness.json").read_text())
            self.assertEqual(result, report)
            html = (site / "index.html").read_text()
            self.assertEqual(html.count('id="fk-official-readiness"'), 1)
            with self.assertRaises(ValueError):
                publish(site, p / "settled.json", p / "gates.json",
                        p / "market.json", now=NOW)

if __name__ == "__main__":
    unittest.main()
