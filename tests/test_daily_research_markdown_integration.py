"""CLI JSON + Cantonese Markdown integration tests."""
import json
import tempfile
import unittest
from pathlib import Path
from ops.daily_research_cli import run

class DailyResearchMarkdownIntegrationTests(unittest.TestCase):
    def test_json_and_markdown_both_generated(self):
        with tempfile.TemporaryDirectory() as d:
            inp, out, md = (Path(d)/name for name in ("in.json","out.json","out.md"))
            inp.write_text(json.dumps({
                "generated_utc": "2026-10-21T10:00:00Z",
                "rows": [{"fixture_id": "f1", "home_team": "Home", "away_team": "Away",
                          "kickoff_utc": "2026-10-21T12:00:00Z", "quote": None}]
            }), encoding="utf-8")
            report = run(inp, out, markdown_path=md)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")), report)
            body = md.read_text(encoding="utf-8")
            self.assertIn("Home vs Away", body)
            self.assertIn("無可用報價", body)
            self.assertIn("未經驗證", body)
            self.assertIn("HOLD", body)

    def test_markdown_cannot_overwrite_input(self):
        with tempfile.TemporaryDirectory() as d:
            inp, out = Path(d)/"in.json", Path(d)/"out.json"
            inp.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                run(inp, out, markdown_path=inp)
            self.assertEqual(inp.read_text(encoding="utf-8"), "{}")

    def test_markdown_cannot_overwrite_json(self):
        with tempfile.TemporaryDirectory() as d:
            inp, out = Path(d)/"in.json", Path(d)/"out.json"
            inp.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                run(inp, out, markdown_path=out)
            self.assertFalse(out.exists())

    def test_invalid_input_does_not_write_either_output(self):
        with tempfile.TemporaryDirectory() as d:
            inp, out, md = (Path(d)/name for name in ("in.json","out.json","out.md"))
            inp.write_text('{"generated_utc":"2026-10-21T10:00:00Z","rows":{}}',
                           encoding="utf-8")
            with self.assertRaises(ValueError):
                run(inp, out, markdown_path=md)
            self.assertFalse(out.exists())
            self.assertFalse(md.exists())

if __name__ == "__main__":
    unittest.main()
