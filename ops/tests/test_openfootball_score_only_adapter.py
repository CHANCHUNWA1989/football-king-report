"""Synthetic JSON tests for score-only historical adapter."""
import json
import tempfile
import unittest
from pathlib import Path
from ops.openfootball_score_only_adapter import evaluate_openfootball_json


class OpenfootballScoreOnlyTests(unittest.TestCase):
    def evaluate(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matches.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return evaluate_openfootball_json(path)

    def test_score_only_totals(self):
        result = self.evaluate({"matches": [
            {"score": {"ft": [2, 1]}}, {"score": {"ft": [0, 0]}},
            {"score": {"ft": [1, 1]}}]})
        self.assertEqual(result["valid_matches"], 3)
        self.assertEqual(result["over_2_5"], 1)
        self.assertEqual(result["under_2_5"], 2)
        self.assertEqual(result["draw"], 2)
        self.assertFalse(result["roi_available"])

    def test_reject_invalid(self):
        result = self.evaluate({"matches": [{"score": {"ft": [-1, 2]}}]})
        self.assertEqual(result["status"], "HOLD")

    def test_skip_unplayed(self):
        result = self.evaluate({"matches": [{"score": {"ft": [2, 2]}}, {"score": {"ft": None}}]})
        self.assertEqual(result["valid_matches"], 1)
        self.assertEqual(result["skipped_rows"], 1)


if __name__ == "__main__":
    unittest.main()
