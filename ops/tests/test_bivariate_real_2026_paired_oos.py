"""Synthetic input tests for honest REUSED real-date-split comparator."""
import copy
from datetime import date, timedelta
from types import SimpleNamespace
import unittest

from ops.bivariate_real_2026_paired_oos import (
    MODEL_NAMES, MARKETS, evaluate, audit,
)


def rows():
    teams = ("a", "b", "c", "d")
    start = date(2025, 6, 1)
    train = []
    for i in range(40):
        train.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "home": teams[i % 4], "away": teams[(i + 1) % 4],
            "score_ft": [i % 4, (i // 3) % 3],
        })
    test_start = date(2026, 2, 1)
    test = []
    for i in range(8):
        test.append({
            "date": (test_start + timedelta(days=i)).isoformat(),
            "home": teams[i % 4], "away": teams[(i + 1) % 4],
            "score_ft": [i % 3, (i + 1) % 3],
        })
    return train, test


class RealisticSyntheticGrid:
    def __init__(self):
        self.grid = [[0.0 for _ in range(15)] for _ in range(15)]
        self.grid[0][0] = 0.2
        self.grid[1][0] = 0.3
        self.grid[0][1] = 0.2
        self.grid[2][1] = 0.3
        self.home_draw_away = (0.6, 0.2, 0.2)


class FakeModel:
    calls = []

    def __init__(self, hg, ag, h, a, *, weights=None):
        self.calls.append({
            "home_goals": tuple(hg), "away_goals": tuple(ag),
            "home_teams": tuple(h), "away_teams": tuple(a),
            "weights": None if weights is None else tuple(weights),
        })

    def fit(self):
        pass

    def predict(self, home, away, *, max_goals=15, normalize=True):
        assert max_goals == 15 and normalize is True
        return RealisticSyntheticGrid()


FakePackage = SimpleNamespace(
    PoissonGoalsModel=FakeModel, DixonColesGoalModel=FakeModel,
    BivariatePoissonGoalModel=FakeModel,
)


class PairedRealHoldoutContractTests(unittest.TestCase):
    def setUp(self):
        FakeModel.calls = []

    def test_all_model_market_pairs_same_heldout_and_hold_contract(self):
        train, test = rows()
        before = copy.deepcopy((train, test))
        result = evaluate(train, test, model_module=FakePackage,
                          min_train=30, min_test=5)
        self.assertEqual((train, test), before)
        self.assertEqual(result["paired_test_games"], 8)
        self.assertEqual(set(result["model_reports"]), set(MODEL_NAMES))
        for model in MODEL_NAMES:
            self.assertEqual(set(result["model_reports"][model]),
                             {key for key, _ in MARKETS})
            for market, _ in MARKETS:
                record = result["model_reports"][model][market]
                self.assertEqual(record["n"], 8)
                self.assertGreaterEqual(record["mean_brier"], 0)
                self.assertGreaterEqual(record["mean_logloss"], 0)
        self.assertEqual(len(FakeModel.calls), 4)
        self.assertEqual([x["weights"] is not None for x in FakeModel.calls],
                         [False, False, False, True])
        self.assertTrue(result["date_split_only_not_true_witnessed_prematch"])
        self.assertEqual(result["fixed_hypothetical_markets_not_tradable_quotes"],
                         ["1X2", "OVER_2.75", "AH_HOME_-0.25"])

    def test_test_score_never_enters_any_model_fit(self):
        train, test = rows()
        evaluate(train, test, model_module=FakePackage, min_train=30, min_test=5)
        captured = copy.deepcopy(FakeModel.calls)
        FakeModel.calls = []
        test[0]["score_ft"] = [9, 0]
        evaluate(train, test, model_module=FakePackage, min_train=30, min_test=5)
        self.assertEqual(captured, FakeModel.calls)
        for fit in FakeModel.calls:
            self.assertEqual(len(fit["home_goals"]), 40)
            self.assertNotIn(9, fit["home_goals"])

    def test_bad_train_or_test_year_rejected_before_fit(self):
        for field in ("train", "heldout"):
            train, test = rows()
            if field == "train":
                train[0]["date"] = "2026-01-01"
            else:
                test[0]["date"] = "2025-12-31"
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, "INVALID_REAL_SCORE_OR_DATE"):
                evaluate(train, test, model_module=FakePackage,
                         min_train=30, min_test=5)
        self.assertEqual(FakeModel.calls, [])

    def test_duplicate_and_boolean_score_rejected_before_fit(self):
        for name in ("duplicate", "boolean"):
            train, test = rows()
            if name == "duplicate":
                train[-1] = copy.deepcopy(train[0])
            else:
                test[0]["score_ft"][1] = True
            with self.subTest(name=name), self.assertRaises(ValueError):
                evaluate(train, test, model_module=FakePackage,
                         min_train=30, min_test=5)
        self.assertEqual(FakeModel.calls, [])

    def test_insufficient_coverage_and_source_failure_are_explicit(self):
        train, test = rows()
        for row in test:
            row["away"] = "never_in_training"
        with self.assertRaisesRegex(ValueError, "INSUFFICIENT_PAIRED_TEAM_COVERAGE"):
            evaluate(train, test, model_module=FakePackage,
                     min_train=30, min_test=5)
        report = audit(source_reader=lambda: (_ for _ in ()).throw(
                       ValueError("source unavailable")), model_module=FakePackage)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "REAL_PAIRED_DATE_SPLIT_BLOCKED")
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["original_holdout_is_untouched_confirmatory"])
        self.assertEqual(FakeModel.calls, [])


if __name__ == "__main__":
    unittest.main()
