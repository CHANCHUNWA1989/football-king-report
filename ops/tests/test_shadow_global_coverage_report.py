import json
import tempfile
import unittest
from pathlib import Path
from shadow_global_source_collector import collect
from shadow_global_coverage_report import summarize

class GlobalCoverageTests(unittest.TestCase):
    def test_six_sources_verified_raw_not_results(self):
        with tempfile.TemporaryDirectory() as folder:
            collect(2026,folder,getter=lambda url:b'{"matches":[{},{}]}')
            report=summarize(folder)
            self.assertEqual(report["successful_leagues"],6)
            self.assertFalse(report["eligible_for_model_scoring"])
            self.assertTrue(all(x["raw_matches"]==2 and x["verified_results"]==0 for x in report["leagues"]))
    def test_tampered_raw_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            collect(2026,folder,getter=lambda url:b'{"matches":[]}')
            (Path(folder)/"eng-premier.json").write_text('{"matches":[{}]}')
            with self.assertRaisesRegex(ValueError,"GLOBAL_RAW_HASH_MISMATCH"):
                summarize(folder)
    def test_duplicate_league_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            collect(2026,folder,getter=lambda url:b'{"matches":[]}')
            p=Path(folder)/"manifest.json"
            m=json.loads(p.read_text())
            m["leagues"][1]["league"]="eng-premier"
            p.write_text(json.dumps(m))
            with self.assertRaisesRegex(ValueError,"UNKNOWN_OR_DUPLICATE_LEAGUE"):
                summarize(folder)
    def test_partial_failure_keeps_hold(self):
        with tempfile.TemporaryDirectory() as folder:
            collect(2026,folder,getter=lambda url:b"not-json")
            report=summarize(folder)
            self.assertEqual(report["successful_leagues"],0)
            self.assertEqual(report["status"],"HOLD")
if __name__=="__main__":
    unittest.main()
