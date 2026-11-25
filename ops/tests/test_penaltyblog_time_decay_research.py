import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ops.penaltyblog_time_decay_research import SCHEMA, XI_PER_DAY, compare, main


def fixture():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    teams = ("a", "b", "c", "d")
    rows = []
    for i in range(40):
        home, away = teams[i % 4], teams[(i + 1) % 4]
        kickoff = start + timedelta(days=i)
        rows.append({
            "source_namespace": "synthetic", "event_id": "past-" + str(i),
            "league_id": "test", "home_team_id": home, "away_team_id": away,
            "kickoff_utc": kickoff.isoformat(),
            "result_recorded_utc": (kickoff + timedelta(hours=3)).isoformat(),
            "home_goals": i % 4, "away_goals": i % 3,
        })
    kickoff = start + timedelta(days=50)
    return {
        "schema": SCHEMA, "production_recommendations": "DISABLED",
        "model": "poisson", "as_of_utc": (kickoff-timedelta(hours=2)).isoformat(),
        "target_fixture": {
            "source_namespace": "synthetic", "event_id": "future-50",
            "league_id": "test", "home_team_id": "a", "away_team_id": "b",
            "kickoff_utc": kickoff.isoformat(),
        }, "historical_matches": rows,
    }


class FakeGrid:
    def __init__(self, values):
        self.home_draw_away = values


class FakeModel:
    calls = []

    def __init__(self, home_goals, away_goals, home_teams, away_teams, *, weights=None):
        self.weights = weights
        self.calls.append({
            "n": len(home_goals),
            "weights": None if weights is None else list(weights),
        })

    def fit(self):
        pass

    def predict(self, home, away, **kwargs):
        if self.weights is None:
            return FakeGrid((0.5, 0.3, 0.2))
        return FakeGrid((0.48, 0.32, 0.2))


class FailingWeightedModel(FakeModel):
    def __init__(self, *args, **kwargs):
        if kwargs.get("weights") is not None:
            raise RuntimeError("synthetic fit failure")
        super().__init__(*args, **kwargs)


class TimeDecayResearchTests(unittest.TestCase):
    def setUp(self):
        FakeModel.calls = []

    def test_same_cohort_both_models_and_monotonic_weights(self):
        source = fixture()
        original = copy.deepcopy(source)
        result = compare(source, model_factory=FakeModel)
        self.assertEqual(source, original)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "UNVERIFIED_MODEL_COMPARISON_ONLY")
        self.assertEqual(result["model_id"], "penaltyblog-poisson-time-decay-sidecar-v1")
        self.assertEqual(result["decay_xi_per_day"], XI_PER_DAY)
        self.assertEqual(result["training_match_count"], 40)
        self.assertEqual(result["unweighted_1x2"], [0.5, 0.3, 0.2])
        self.assertEqual(result["weighted_1x2"], [0.48, 0.32, 0.2])
        self.assertEqual(len(FakeModel.calls), 2)
        self.assertIsNone(FakeModel.calls[0]["weights"])
        w = FakeModel.calls[1]["weights"]
        self.assertEqual(len(w), 40)
        self.assertTrue(all(0 < x < 1 for x in w))
        self.assertTrue(all(a < b for a, b in zip(w, w[1:])))
        self.assertLess(result["effective_training_match_count"], 40)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["model_promoted"])
        self.assertFalse(result["source_authenticity_verified"])

    def test_dixon_coles_branch_supported_without_promotion(self):
        data = fixture()
        data["model"] = "dixon_coles"
        result = compare(data, model_factory=FakeModel)
        self.assertEqual(result["model_id"], "penaltyblog-dixon_coles-time-decay-sidecar-v1")
        self.assertEqual(result["status"], "HOLD")

    def test_non_prematch_result_is_rejected_before_any_fit(self):
        data = fixture()
        data["historical_matches"][-1]["result_recorded_utc"] = data["as_of_utc"]
        report = compare(data, model_factory=FakeModel)
        self.assertEqual(report["reason"], "INVALID_OR_UNVERIFIED_INPUT")
        self.assertEqual(FakeModel.calls, [])
        self.assertNotIn("weighted_1x2", report)

    def test_bad_contract_does_not_run_model(self):
        for key, value in (("schema", "another"), ("production_recommendations", "ENABLED"),
                           ("model", "unverified-model")):
            with self.subTest(key=key):
                data = fixture()
                data[key] = value
                self.assertEqual(compare(data, model_factory=FakeModel)["reason"], "INVALID_CONTRACT")
        self.assertEqual(FakeModel.calls, [])

    def test_failed_weighted_fit_never_leaks_baseline_probabilities(self):
        report = compare(fixture(), model_factory=FailingWeightedModel)
        self.assertEqual(report["reason"], "WEIGHTED_FIT_BLOCKED")
        self.assertNotIn("unweighted_1x2", report)
        self.assertNotIn("weighted_1x2", report)
        self.assertFalse(report["positive_ev_verified"])

    def test_offset_equivalent_cutoff_produces_same_weights(self):
        first = fixture()
        shifted = copy.deepcopy(first)
        utc = datetime.fromisoformat(first["as_of_utc"])
        shifted["as_of_utc"] = utc.astimezone(timezone(timedelta(hours=8))).isoformat()
        a = compare(first, model_factory=FakeModel)
        b = compare(shifted, model_factory=FakeModel)
        self.assertEqual(a["effective_training_match_count"], b["effective_training_match_count"])
        self.assertEqual(a["weighted_1x2"], b["weighted_1x2"])

    def test_duplicate_json_key_cli_fails_before_calculation(self):
        bad = json.dumps(fixture()).replace('"model": "poisson"', '"model": "poisson", "model": "dixon_coles"', 1)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.json"
            source.write_text(bad, encoding="utf-8")
            output = io.StringIO()
            with patch("sys.argv", ["decay", "--input", str(source)]), redirect_stdout(output):
                with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                    main()
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(FakeModel.calls, [])


if __name__ == "__main__":
    unittest.main()
