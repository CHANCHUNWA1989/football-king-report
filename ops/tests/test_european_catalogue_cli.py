"""Offline CLI regression tests: no provider requests or API credits."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from ops.european_catalogue_cli import main


class TestEuropeanCatalogueCLI(unittest.TestCase):
    def test_valid_catalogue_remains_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sports.json"
            target = Path(directory) / "report.json"
            source.write_text(json.dumps([{"key": "soccer_epl", "active": True}]), encoding="utf-8")
            self.assertEqual(main(["--catalogue", str(source), "--output", str(target)]), 0)
            report = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "HOLD")
            self.assertEqual(report["production_recommendations"], "DISABLED")
            self.assertTrue(report["catalogue_only"])

    def test_invalid_catalogue_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sports.json"
            source.write_text('{"unexpected":true}', encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(["--catalogue", str(source)])
            self.assertEqual(result, 2)
            self.assertEqual(json.loads(output.getvalue())["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
