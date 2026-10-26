"""The challenger runs inside the existing replay without changing its model."""
import copy
import hashlib
import json
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from retrospective_backtest import DEVELOPMENT, HOLDOUT, LEAGUE_FILES, build


def documents():
    result = {}
    for season, year in ((DEVELOPMENT, 2024), (HOLDOUT, 2025)):
        for league in LEAGUE_FILES:
            clubs = ["A", "B", "C", "D", "E", "F"]
            document = {"matches": [{
                "date": (date(year, 8, 1) + timedelta(days=i // 2)).isoformat(),
                "team1": clubs[i % 6], "team2": clubs[(i + 1) % 6],
                "score": {"ft": [i % 4, (i + 1) % 3]},
            } for i in range(120)]}
            result[(season, league)] = (document, hashlib.sha256(
                json.dumps(document, sort_keys=True).encode()).hexdigest())
    return result


class DixonColesReplayIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = documents()
        cls.before = copy.deepcopy(cls.docs)
        cls.report = build(cls.docs)

    def test_complete_existing_replay_emits_separate_candidate_on_same_cases(self):
        candidate = self.report["dixon_coles_challenger"]
        self.assertIsNotNone(candidate["selected_rho"])
        self.assertEqual(self.docs, self.before)
        self.assertFalse(self.report["automatic_model_promotion"])
        self.assertEqual(self.report["production_recommendations"], "DISABLED")
        for season in (DEVELOPMENT, HOLDOUT):
            cohort = candidate["cohorts"][season]
            self.assertEqual(cohort["n"], self.report["cohorts"][season]["n"])
            for key in ("original", "derived_rho0", "candidate", "league_frequency"):
                self.assertEqual(cohort["models"][key]["n"], cohort["n"])
            self.assertEqual(cohort["models"]["original"]["mean_log_loss"],
                             self.report["cohorts"][season]["original"]["mean_log_loss"])
        self.assertEqual(set(candidate["by_league"]), set(LEAGUE_FILES))
        json.dumps(self.report, allow_nan=False)

    def test_changing_all_assessment_results_does_not_retune_development(self):
        changed = copy.deepcopy(self.docs)
        for (season, _), (document, _) in changed.items():
            if season == HOLDOUT:
                for match in document["matches"]:
                    match["score"]["ft"] = [0, 20]
        altered = build(changed)["dixon_coles_challenger"]
        original = self.report["dixon_coles_challenger"]
        self.assertEqual(altered["development_fit"], original["development_fit"])
        self.assertEqual(altered["selected_rho"], original["selected_rho"])
        self.assertEqual(altered["cohorts"][DEVELOPMENT], original["cohorts"][DEVELOPMENT])

    def test_missing_archive_cannot_silently_fit_a_smaller_population(self):
        partial = dict(self.docs)
        del partial[(HOLDOUT, "epl")]
        report = build(partial)
        candidate = report["dixon_coles_challenger"]
        self.assertIsNone(candidate["selected_rho"])
        self.assertIn("HOLD", candidate["status"])
        self.assertIn(HOLDOUT + "/epl", report["missing_archive_scopes"])
        empty = build({})["dixon_coles_challenger"]
        self.assertIsNone(empty["selected_rho"])
        self.assertIn("HOLD", empty["status"])


if __name__ == "__main__":
    unittest.main()
