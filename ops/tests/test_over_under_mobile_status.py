import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from over_under_mobile_status import publish

class MobileStatusTests(unittest.TestCase):
    def test_visible_and_idempotent(self):
        with TemporaryDirectory() as d:
            p=Path(d)
            (p/"index.html").write_text("<html><body><main>Hi</main></body></html>")
            (p/"over_under_25.json").write_text(json.dumps({"candidate_count":0,
                "input_status":"NO_VERIFIED_MARKET_INPUT","generated_at_utc":"2026-10-15T12:00:00Z"}))
            publish(p)
            publish(p)
            html=(p/"index.html").read_text()
            self.assertEqual(html.count('id="fk-ou25"'),1)
            self.assertIn("over_under_25.json",html)
            self.assertIn("正式投注推薦：停用",html)

if __name__=="__main__":
    unittest.main()
