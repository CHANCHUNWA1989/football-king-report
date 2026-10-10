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
        outcome = compare(self.a, self.b)
        self.assertEqual(outcome["score_comparisons"], 1)
        self.assertEqual(outcome["score_conflicts"], 0)
        self.assertEqual(outcome["two_publisher_matching_ft_candidate_count"], 1)
        self.assertEqual(outcome["two_publisher_matching_ft_candidates"][0]["score_ft"], [2, 1])

    def test_disagreeing_scores_do_not_create_verified_candidate(self):
        self.b[0]["score_ft"] = [2, 0]
        outcome = compare(self.a, self.b)
        self.assertEqual(outcome["score_conflicts"], 1)
        self.assertEqual(outcome["two_publisher_matching_ft_candidate_count"], 0)

    def test_duplicate_rows_never_create_score_candidates(self):
        self.b.append(dict(self.b[0]))
        outcome = compare(self.a, self.b)
        self.assertEqual(outcome["two_publisher_matching_ft_candidate_count"], 0)

    def test_score_conflict_detected(self):
        self.b[0]["score_ft"] = [1, 3]
        self.assertEqual(compare(self.a, self.b)["score_conflicts"], 1)

    def test_invalid_scores_not_counted_as_independent_result_evidence(self):
        for score in ([True, 0], ["2", 1], [3.5, 1], [-1, 0],
                      [31, 0], [2], "2-1", None):
            with self.subTest(score=repr(score)):
                self.a[0]["score_ft"] = score
                result = compare(self.a, self.b)
                self.assertEqual(result["matched_identical_home_away"], 1)
                self.assertEqual(result["score_comparisons"], 0)
                self.assertEqual(result["score_conflicts"], 0)

    def test_explicitly_unfinished_score_not_used_as_final_result(self):
        self.a[0]["status"] = "LIVE"
        result = compare(self.a, self.b)
        self.assertEqual(result["score_comparisons"], 0)
        self.a[0]["status"] = "FINISHED"
        self.assertEqual(compare(self.a, self.b)["score_comparisons"], 1)

    def test_duplicate_source_a_fixtures_are_ambiguous(self):
        self.a.append(dict(self.a[0]))
        result = compare(self.a, self.b)
        self.assertEqual(result["matched_identical_home_away"], 0)
        self.assertEqual(result["score_comparisons"], 0)

    def test_duplicate_source_b_fixtures_are_ambiguous(self):
        self.b.append(dict(self.b[0]))
        result = compare(self.a, self.b)
        self.assertEqual(result["matched_identical_home_away"], 0)
        self.assertEqual(result["score_comparisons"], 0)

    def test_adjacent_date_ambiguity_is_not_selected_by_order(self):
        self.a.append({**self.a[0], "date": "2026-10-03"})
        result = compare(self.a, self.b)
        self.assertEqual(result["matched_identical_home_away"], 0)

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
