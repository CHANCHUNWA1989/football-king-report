import json
import tempfile
import unittest
from pathlib import Path
from ops.result_verification_cli import main

class ResultVerificationCliTests(unittest.TestCase):
    def test_writes_research_only_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = root / "fixtures.json"
            observations = root / "observations.json"
            output = root / "out.json"
            fixtures.write_text(json.dumps([{"fixture_id":"f1","kickoff_utc":"2026-10-10T12:00:00Z"}]))
            observations.write_text("[]")
            result = main(["--fixtures",str(fixtures),"--observations",str(observations),"--output",str(output)])
            saved = json.loads(output.read_text())
            self.assertEqual(saved["verified_count"],0)
            self.assertEqual(saved["production_recommendations"],"DISABLED")
            self.assertEqual(result["results"][0]["status"],"HOLD")
