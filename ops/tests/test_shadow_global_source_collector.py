import hashlib
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from shadow_global_source_collector import LEAGUES,collect

class GlobalCollectorTests(unittest.TestCase):
    def test_six_leagues_remain_unverified(self):
        raw=b'{"matches":[{"date":"2026-10-14"}]}'
        with tempfile.TemporaryDirectory() as folder:
            result=collect(2026,folder,getter=lambda url:raw,
                           now=datetime(2026,10,14,tzinfo=timezone.utc))
            self.assertEqual(len(result["leagues"]),6)
            self.assertEqual(set(LEAGUES),{x["league"] for x in result["leagues"]})
            self.assertFalse(result["eligible_for_model_scoring"])
            self.assertFalse(result["independently_verified"])
            self.assertEqual(result["production_recommendations"],"DISABLED")
            for item in result["leagues"]:
                self.assertEqual(item["raw_sha256"],hashlib.sha256(raw).hexdigest())
                self.assertEqual((Path(folder)/item["raw_file"]).read_bytes(),raw)
    def test_bad_payload_quarantined_per_league(self):
        with tempfile.TemporaryDirectory() as folder:
            result=collect(2026,folder,getter=lambda url:b"not-json")
            self.assertEqual(len(result["leagues"]),6)
            self.assertTrue(all(x["status"]=="ERROR" for x in result["leagues"]))
    def test_invalid_year_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            for year in (True,1999,2101):
                with self.subTest(year=year),self.assertRaisesRegex(ValueError,"INVALID_SEASON"):
                    collect(year,folder)
if __name__=="__main__":
    unittest.main()
