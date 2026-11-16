import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from ops.penaltyblog_bivariate_goals_challenger import (
    SCHEMA, _settle, compare, main,
)
from ops.tests.test_penaltyblog_time_decay_research import fixture as base_fixture


def fixture():
    data = base_fixture()
    data["schema"] = SCHEMA
    data["model"] = "bivariate_poisson"
    return data


def grid(weighted=False):
    # 15x15, row=home goals, column=away goals.
    matrix = [[0.0 for _ in range(15)] for _ in range(15)]
    matrix[1][0] = 0.3
    matrix[1][1] = 0.3 if weighted else 0.2
    matrix[2][1] = 0.2 if weighted else 0.3
    matrix[0][1] = 0.2
    return matrix


class FakeGrid:
    def __init__(self, weighted=False, invalid=False):
        self.grid = grid(weighted=weighted)
        if invalid:
            self.grid[0][1] = float("nan")
        self.home_draw_away = [0.5 if weighted else 0.6,
                               0.3 if weighted else 0.2, 0.2]


class FakeModel:
    calls = []

    def __init__(self, home_goals, away_goals, home_teams, away_teams, weights=None):
        self.weights = weights
        self.calls.append({
            "training_n": len(home_goals),
            "weights": None if weights is None else list(weights),
        })

    def fit(self):
        pass

    def predict(self, home, away, *, max_goals=15, normalize=True):
        assert max_goals == 15
        assert normalize is True
        return FakeGrid(self.weights is not None)


class FaultyWeightedModel(FakeModel):
    def fit(self):
        if self.weights is not None:
            raise RuntimeError("failed weighted fit")


class BrokenGridModel(FakeModel):
    def predict(self, *args, **kwargs):
        return FakeGrid(invalid=True)


class BivariateChallengerTests(unittest.TestCase):
    def setUp(self):
        FakeModel.calls = []

    def test_both_variants_same_history_and_settlement_math(self):
        source = fixture()
        frozen_input = copy.deepcopy(source)
        report = compare(source, model_factory=FakeModel)
        self.assertEqual(source, frozen_input)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["reason"], "UNVERIFIED_BIVARIATE_RESEARCH_ONLY")
        self.assertEqual(report["model_id"], "penaltyblog-bivariate-poisson-paired-decay-v1")
        self.assertEqual([x["training_n"] for x in FakeModel.calls], [40, 40])
        self.assertIsNone(FakeModel.calls[0]["weights"])
        weights = FakeModel.calls[1]["weights"]
        self.assertEqual(len(weights), 40)
        self.assertTrue(all(a < b for a, b in zip(weights, weights[1:])))
        self.assertEqual(report["models"]["unweighted"]["probabilities_1x2_home_draw_away"],
                         [0.6, 0.2, 0.2])
        self.assertEqual(report["models"]["time_weighted"]["probabilities_1x2_home_draw_away"],
                         [0.5, 0.3, 0.2])
        over275 = report["models"]["unweighted"]["over_total_goals_settlement"]["2.75"]
        self.assertEqual(over275["full_loss"], 0.7)
        self.assertEqual(over275["half_win"], 0.3)
        self.assertEqual(over275["full_win"], 0.0)
        ah = report["models"]["unweighted"]["home_asian_handicap_settlement"]["-0.25"]
        self.assertEqual(ah["full_win"], 0.6)
        self.assertEqual(ah["half_loss"], 0.2)
        self.assertEqual(ah["full_loss"], 0.2)
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertFalse(report["positive_ev_verified"])
        self.assertFalse(report["model_promoted"])
        self.assertFalse(report["source_authenticity_verified"])
        self.assertNotIn("stake", report)

    def test_quarter_lines_exact_unit_outcomes(self):
        checks = [
            ("over", 1, 1, 2.75, "full_loss"),
            ("over", 2, 1, 2.75, "half_win"),
            ("over", 3, 1, 2.75, "full_win"),
            ("over", 1, 1, 2.25, "half_loss"),
            ("over", 2, 1, 3.0, "push"),
            ("home_handicap", 1, 1, -0.25, "half_loss"),
            ("home_handicap", 2, 1, -0.75, "half_win"),
            ("home_handicap", 1, 1, 0.25, "half_win"),
            ("home_handicap", 1, 2, 1.0, "push"),
            ("home_handicap", 1, 2, -0.5, "full_loss"),
        ]
        for kind, home, away, line, expected in checks:
            with self.subTest(kind=kind, score=(home, away), line=line):
                self.assertEqual(_settle(kind, home, away, line), expected)

    def test_prematch_cutoff_prevents_lookahead(self):
        source = fixture()
        source["historical_matches"][-1]["result_recorded_utc"] = source["as_of_utc"]
        self.assertEqual(compare(source, model_factory=FakeModel)["reason"],
                         "INVALID_OR_UNVERIFIED_INPUT")
        self.assertEqual(FakeModel.calls, [])

    def test_duplicate_fixture_or_scores_rejected_before_fit(self):
        for change in ("duplicate", "boolean_goal", "different_league"):
            source = fixture()
            if change == "duplicate":
                source["historical_matches"][-1]["event_id"] = source["historical_matches"][0]["event_id"]
            elif change == "boolean_goal":
                source["historical_matches"][0]["home_goals"] = True
            else:
                source["historical_matches"][-1]["league_id"] = "other"
            with self.subTest(change=change):
                self.assertEqual(compare(source, model_factory=FakeModel)["reason"],
                                 "INVALID_OR_UNVERIFIED_INPUT")
        self.assertEqual(FakeModel.calls, [])

    def test_invalid_contract_does_not_fit(self):
        for key, value in (("schema", "other"),
                           ("model", "bayesian"),
                           ("production_recommendations", "ENABLED")):
            source = fixture()
            source[key] = value
            self.assertEqual(compare(source, model_factory=FakeModel)["reason"],
                             "INVALID_CONTRACT")
        self.assertEqual(FakeModel.calls, [])

    def test_partial_fit_or_nonfinite_grid_fails_whole_cohort(self):
        for klass in (FaultyWeightedModel, BrokenGridModel):
            result = compare(fixture(), model_factory=klass)
            self.assertEqual(result["reason"], "BIVARIATE_FIT_OR_GRID_VALIDATION_FAILED")
            self.assertNotIn("models", result)
            self.assertFalse(result["positive_ev_verified"])

    def test_same_instant_timezone_variant_equal_probabilities(self):
        from datetime import datetime, timezone, timedelta
        original = fixture()
        altered = copy.deepcopy(original)
        t = datetime.fromisoformat(original["as_of_utc"])
        altered["as_of_utc"] = t.astimezone(timezone(timedelta(hours=8))).isoformat()
        a = compare(original, model_factory=FakeModel)
        b = compare(altered, model_factory=FakeModel)
        self.assertEqual(a["models"], b["models"])
        self.assertEqual(a["effective_weighted_sample_size"],
                         b["effective_weighted_sample_size"])

    def test_duplicate_json_cli_refuses_before_model(self):
        source = json.dumps(fixture()).replace(
            '"model": "bivariate_poisson"',
            '"model": "bivariate_poisson", "model": "poisson"', 1)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "input.json"
            p.write_text(source, encoding="utf-8")
            buffer = io.StringIO()
            with patch("sys.argv", ["bivariate", "--input", str(p)]), redirect_stdout(buffer):
                with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                    main()
            self.assertEqual(buffer.getvalue(), "")
            self.assertEqual(FakeModel.calls, [])


if __name__ == "__main__":
    unittest.main()
