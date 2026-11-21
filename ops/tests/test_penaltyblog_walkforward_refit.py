import copy
import io
import json
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
from ops.penaltyblog_walkforward_refit import main, refit_walkforward


def cohort():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    teams = ["a", "b", "c", "d"]
    history = []
    for i in range(48):
        kickoff = base + timedelta(days=i)
        home, away = teams[i % 4], teams[(i + 1 + (i // 4) % 2) % 4]
        if home == away:
            away = teams[(i + 2) % 4]
        history.append({
            "source_namespace": "synthetic", "event_id": f"history-{i}",
            "league_id": "synthetic", "home_team_id": home, "away_team_id": away,
            "kickoff_utc": kickoff.isoformat(),
            "result_recorded_utc": (kickoff + timedelta(hours=3)).isoformat(),
            "home_goals": i % 4, "away_goals": i % 3,
        })
    targets = []
    for i in (49, 50):
        kickoff = base + timedelta(days=i)
        targets.append({
            "source_namespace": "synthetic", "event_id": f"target-{i}",
            "league_id": "synthetic", "home_team_id": "a", "away_team_id": "b",
            "kickoff_utc": kickoff.isoformat(),
            "as_of_utc": (kickoff - timedelta(hours=2)).isoformat(),
        })
    return {"schema": "football-king-penaltyblog-walkforward-v1",
            "production_recommendations": "DISABLED", "model": "poisson",
            "historical_matches": history, "targets": targets, "min_training": 30}


class FakeGrid:
    home_draw_away = (.5, .3, .2)


class FakeModel:
    calls = []
    def __init__(self, home_goals, away_goals, home_teams, away_teams):
        self.calls.append(len(home_goals))
    def fit(self):
        pass
    def predict(self, home, away, **kwargs):
        return FakeGrid()


@contextmanager
def cli_input(raw):
    dependency = ModuleType("penaltyblog")
    dependency.models = SimpleNamespace(PoissonGoalsModel=FakeModel,
                                       DixonColesGoalModel=FakeModel)
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "synthetic.json"
        source.write_text(raw, encoding="utf-8")
        output = io.StringIO()
        with patch("sys.argv", ["walkforward", "--input", str(source)]), \
                patch.dict("sys.modules", {"penaltyblog": dependency}), \
                redirect_stdout(output):
            yield source, output


class WalkForwardRefitTests(unittest.TestCase):
    def setUp(self):
        FakeModel.calls = []

    def test_refits_each_target_with_valid_history(self):
        result = refit_walkforward(cohort(), model_factory=FakeModel)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["refit_count"], 2)
        self.assertEqual(FakeModel.calls, [48, 48])
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["independent_provenance_verified"])

    def test_unavailable_result_excluded_before_fit(self):
        data = cohort()
        data["historical_matches"][-1]["result_recorded_utc"] = "2026-02-21T23:00:00Z"
        result = refit_walkforward(data, model_factory=FakeModel)
        self.assertEqual(result["refit_count"], 2)
        self.assertEqual(FakeModel.calls, [47, 47])

    def test_insufficient_history_fails_closed(self):
        data = cohort()
        data["min_training"] = 49
        result = refit_walkforward(data, model_factory=FakeModel)
        self.assertEqual(result["reason"], "INSUFFICIENT_AVAILABLE_HISTORY")
        self.assertNotIn("predictions", result)

    def test_target_after_kickoff_fails(self):
        data = cohort()
        data["targets"][0]["as_of_utc"] = "2026-02-25T00:00:00Z"
        self.assertEqual(refit_walkforward(data, model_factory=FakeModel)["reason"],
                         "TARGET_ORDER_OR_LOOKAHEAD")

    def test_duplicate_target_fails(self):
        data = cohort()
        data["targets"].append(copy.deepcopy(data["targets"][-1]))
        self.assertEqual(refit_walkforward(data, model_factory=FakeModel)["reason"],
                         "DUPLICATE_OR_OVERLAPPING_TARGET")

    def test_history_overlap_fails(self):
        data = cohort()
        data["targets"][0]["event_id"] = data["historical_matches"][0]["event_id"]
        self.assertEqual(refit_walkforward(data, model_factory=FakeModel)["reason"],
                         "DUPLICATE_OR_OVERLAPPING_TARGET")

    def test_wrong_source_is_excluded(self):
        data = cohort()
        data["historical_matches"][0]["source_namespace"] = "other"
        result = refit_walkforward(data, model_factory=FakeModel)
        self.assertEqual(result["refit_count"], 2)
        self.assertEqual(FakeModel.calls, [47, 47])

    def test_model_failure_holds(self):
        class BadModel(FakeModel):
            def fit(self):
                raise RuntimeError("bad fit")
        self.assertEqual(refit_walkforward(cohort(), model_factory=BadModel)["reason"],
                         "REFIT_FAILED_OR_INVALID_TRAINING")

    def test_invalid_production_flag_holds(self):
        data = cohort()
        data["production_recommendations"] = "ENABLED"
        self.assertEqual(refit_walkforward(data, model_factory=FakeModel)["reason"],
                         "INVALID_CONTRACT")

    def test_cli_unique_json_preserves_research_report_and_source(self):
        data = cohort()
        expected = refit_walkforward(data, model_factory=FakeModel)
        FakeModel.calls = []
        raw = json.dumps(data)
        with cli_input(raw) as (source, output):
            main()
            self.assertEqual(json.loads(output.getvalue()), expected)
            self.assertEqual(source.read_text(encoding="utf-8"), raw)
        self.assertEqual(FakeModel.calls, [48, 48])
        self.assertEqual(expected["status"], "HOLD")
        self.assertFalse(expected["positive_ev_verified"])
        self.assertEqual(expected["production_recommendations"], "DISABLED")

    def test_cli_duplicate_json_fields_rejected_before_refit_or_output(self):
        data = cohort()
        raw = json.dumps(data)
        cutoff = json.dumps(data["targets"][0]["as_of_utc"])
        replacements = (
            ('"model": "poisson"', '"model": "unsupported", "model": "poisson"'),
            ('"model": "poisson"', '"model": "poisson", "model": "poisson"'),
            (f'"as_of_utc": {cutoff}',
             f'"as_of_utc": "2099-01-01T00:00:00Z", "as_of_utc": {cutoff}'),
            ('"home_goals": 0', '"home_goals": true, "home_goals": 0'),
            ('"source_namespace": "synthetic"',
             '"source_namespace": "other", "source_namespace": "synthetic"'),
            ('"event_id": "history-0"',
             '"event_\\u0069d": "other", "event_id": "history-0"'),
        )
        for old, new in replacements:
            with self.subTest(field=old, replacement=new):
                FakeModel.calls = []
                malformed = raw.replace(old, new, 1)
                self.assertNotEqual(malformed, raw)
                with cli_input(malformed) as (source, output):
                    with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                        main()
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(FakeModel.calls, [])
                    self.assertEqual(source.read_text(encoding="utf-8"), malformed)


if __name__ == "__main__":
    unittest.main()
