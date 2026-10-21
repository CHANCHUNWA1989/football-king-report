"""Provider export one-command end-to-end tests."""
import json
import tempfile
import unittest
from pathlib import Path
from ops.provider_research_cli import run

NOW="2026-10-21T10:00:00Z"
def export(quotes):
    return {"source":"offline-test-export","fixtures":[{
        "id":"fixture1","home":"Home","away":"Away",
        "kickoff_utc":"2026-10-21T12:00:00Z","quotes":quotes
    }]}
def quote():
    return {"id":"quote1","bookmaker":"Book","market":"TOTALS",
            "selection":"OVER","line":2.5,"decimal_odds":1.9,
            "quote_utc":"2026-10-21T09:55:00Z"}

class ProviderResearchCliTests(unittest.TestCase):
    def test_end_to_end_quote_and_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            inp,out,md=(Path(d)/x for x in ("source.json","report.json","report.md"))
            inp.write_text(json.dumps(export([quote()])),encoding="utf-8")
            result=run(inp,out,md,generated_utc=NOW)
            body=md.read_text(encoding="utf-8")
            self.assertEqual(result["production_recommendations"],"HOLD")
            self.assertFalse(result["positive_ev_verified"])
            for expected in ("offline-test-export","quote1","1.9","HOLD","未經驗證"):
                self.assertIn(expected,body)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8")),result)

    def test_empty_quote_yields_no_recommendation(self):
        with tempfile.TemporaryDirectory() as d:
            inp,out,md=(Path(d)/x for x in ("source.json","report.json","report.md"))
            inp.write_text(json.dumps(export([])),encoding="utf-8")
            result=run(inp,out,md,generated_utc=NOW)
            self.assertEqual(result["cards"][0]["status"],"NO_RECOMMENDATION")
            self.assertIn("無可用報價",md.read_text(encoding="utf-8"))

    def test_collision_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            inp,out=(Path(d)/x for x in ("source.json","report.json"))
            inp.write_text(json.dumps(export([quote()])),encoding="utf-8")
            with self.assertRaises(ValueError):
                run(inp,out,inp,generated_utc=NOW)
            self.assertFalse(out.exists())

    def test_invalid_export_no_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            inp,out,md=(Path(d)/x for x in ("source.json","report.json","report.md"))
            inp.write_text('{"fixtures":[]}',encoding="utf-8")
            with self.assertRaises(ValueError):
                run(inp,out,md,generated_utc=NOW)
            self.assertFalse(out.exists())
            self.assertFalse(md.exists())

if __name__=="__main__":
    unittest.main()
