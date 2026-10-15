import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from publish_over_under_25 import publish

class DailyOverUnderTests(unittest.TestCase):
    def test_no_feed_stays_empty(self):
        with TemporaryDirectory() as folder:
            x=publish(folder,now_utc="2026-10-15T12:00:00Z")
            self.assertEqual(x["candidate_count"],0)
            self.assertEqual(x["input_status"],"NO_VERIFIED_MARKET_INPUT")
            self.assertEqual(x["production_recommendations"],"DISABLED")
            self.assertTrue((Path(folder)/"over_under_25.json").exists())
    def test_bad_evidence_blocked(self):
        with TemporaryDirectory() as folder:
            source=Path(folder)/"input.json"
            source.write_text(json.dumps([{"fixture_id":"demo","expected_goals":3,
                "over_odds":2,"under_odds":2}]))
            x=publish(folder,str(source),"2026-10-15T12:00:00Z")
            self.assertEqual(x["candidate_count"],0)
            self.assertEqual(x["results"][0]["status"],"HOLD")

if __name__=="__main__":
    unittest.main()
