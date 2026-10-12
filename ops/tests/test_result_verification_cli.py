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

    def test_rejects_overwriting_original_fixture_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Path(tmp) / "fixtures.json"
            observations = Path(tmp) / "observations.json"
            fixture.write_text("[]")
            observations.write_text("[]")
            with self.assertRaises(SystemExit):
                main(["--fixtures", str(fixture), "--observations", str(observations), "--output", str(fixture)])
            self.assertEqual(fixture.read_text(), "[]")

    def test_existing_report_is_replaced_with_complete_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixtures = root / "fixtures.json"
            observations = root / "observations.json"
            output = root / "out.json"
            fixtures.write_text(json.dumps([{"fixture_id": "f1", "kickoff_utc": "2026-10-10T12:00:00Z"}]))
            observations.write_text("[]")
            output.write_text("{incomplete previous report")
            main(["--fixtures", str(fixtures), "--observations", str(observations), "--output", str(output)])
            report = json.loads(output.read_text())
            self.assertEqual(report["verified_count"], 0)
            self.assertEqual(report["results"][0]["status"], "HOLD")
            self.assertEqual(list(root.glob(".result-audit-*.tmp")), [])
