"""Independent Bundesliga source comparison regression checks."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source_crosscheck import compare, validate_site


class IndependentSourceTests(unittest.TestCase):
    def setUp(self):
        self.a = [{"date": "2026-10-02", "home": "FC Bayern München",
                   "away": "Borussia Dortmund", "score_ft": [2, 1]}]
        self.b = [{"date": "2026-10-02", "home": "FC Bayern Munchen",
                   "away": "Borussia Dortmund", "score_ft": [2, 1]}]

    def test_normalized_names_match(self):
        self.assertEqual(compare(self.a, self.b)["matched_identical_home_away"], 1)

    def test_score_agreement_counts(self):
        self.assertEqual(compare(self.a, self.b)["score_comparisons"], 1)
        self.assertEqual(compare(self.a, self.b)["score_conflicts"], 0)

    def test_score_conflict_detected(self):
        self.b[0]["score_ft"] = [1, 3]
        self.assertEqual(compare(self.a, self.b)["score_conflicts"], 1)

    def test_unmatched_opponents_not_false_conflict(self):
        self.b[0]["away"] = "Different Club"
        self.assertEqual(compare(self.a, self.b)["score_conflicts"], 0)
        self.assertEqual(compare(self.a, self.b)["score_comparisons"], 0)

    def test_conflict_forces_report_hold(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            for file, body in (
                ("quality.json", {"status": "RESEARCH_ONLY", "critical_errors": [], "warnings": []}),
                ("status.json", {"status": "RESEARCH_ONLY", "quality_status": "RESEARCH_ONLY"}),
                ("report.json", {"status": "RESEARCH_ONLY"})):
                (p / file).write_text(json.dumps(body))
            validate_site(p, {"score_conflicts": 1, "score_comparisons": 1,
                              "matched_identical_home_away": 1})
            self.assertEqual(json.loads((p / "status.json").read_text())["status"], "HOLD")
            self.assertEqual(json.loads((p / "quality.json").read_text())["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
