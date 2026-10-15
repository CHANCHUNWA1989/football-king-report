import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from publish_value_research import main

class PublishValueResearchTests(unittest.TestCase):
    def test_missing_market_data_publishes_zero_picks(self):
        with tempfile.TemporaryDirectory() as d:
            with patch("sys.argv",["publish_value_research","--site",d]):
                main()
            result=json.loads((Path(d)/"value_research.json").read_text())
            self.assertEqual(result["candidate_count"],0)
            self.assertEqual(result["input_status"],"NO_VERIFIED_MARKET_INPUT")
            self.assertEqual(result["production_recommendations"],"DISABLED")

if __name__=="__main__":
    unittest.main()
