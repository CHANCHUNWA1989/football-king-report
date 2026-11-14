"""No network/dependency, synthetic fixtures: research-only external baseline."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from ops.penaltyblog_research_bridge import SCHEMA, evaluate, main


def sample():
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    matches = []
    teams = ("club-A", "club-B", "club-C", "club-D")
    for i in range(40):
        when = start + timedelta(days=i)
        matches.append({
            "source_namespace": "test-provider", "event_id": f"past-{i}", "league_id": "epl",
            "home_team_id": teams[i % 4], "away_team_id": teams[(i + 1) % 4],
            "kickoff_utc": when.isoformat(),
            "result_recorded_utc": (when + timedelta(hours=3)).isoformat(),
            "home_goals": i % 3, "away_goals": (i + 1) % 2,
        })
    return {
        "schema": SCHEMA, "production_recommendations": "DISABLED",
        "model": "poisson", "as_of_utc": "2026-10-01T09:00:00Z",
        "target_fixture": {
            "source_namespace": "test-provider", "event_id": "future-1", "league_id": "epl",
            "home_team_id": "club-A", "away_team_id": "club-B",
            "kickoff_utc": "2026-10-01T15:00:00Z",
        },
        "historical_matches": matches,
    }


class FakeGrid:
    home_draw_away = [0.5, 0.3, 0.2]


class FakeModel:
    def __init__(self, home_goals, away_goals, home_teams, away_teams):
        assert len(home_goals) == 40
        assert len(away_goals) == 40
        assert "club-A" in home_teams

    def fit(self):
        pass

    def predict(self, home, away, **kw):
        assert home == "club-A" and away == "club-B"
        assert kw == {"max_goals": 15, "normalize": True}
        return FakeGrid()


class ResearchBridgeTests(unittest.TestCase):
    def test_real_interface_without_promotion_or_bets(self):
        result = evaluate(sample(), model_factory=FakeModel)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["training_match_count"], 40)
        self.assertEqual([result[k] for k in ("p_home", "p_draw", "p_away")], [.5, .3, .2])
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["source_authenticity_verified"])
        self.assertFalse(result["is_sealed_original_forecast"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("ev_per_unit", result)

    def test_reject_future_results_and_cutoff_leakage(self):
        for value in ("2026-10-01T09:00:00Z", "2026-10-02T09:00:00Z"):
            with self.subTest(value=value):
                payload = sample()
                payload["historical_matches"][0]["result_recorded_utc"] = value
                self.assertEqual(evaluate(payload, model_factory=FakeModel)["status"], "HOLD")

    def test_reject_cross_provider_and_duplicate_native_ids(self):
        for changes in ({"source_namespace": "other-provider"}, {"event_id": "past-1"},
                        {"event_id": "future-1"}, {"league_id": "laliga"}):
            with self.subTest(changes=changes):
                payload = sample()
                payload["historical_matches"][0].update(changes)
                self.assertEqual(evaluate(payload, model_factory=FakeModel)["status"], "HOLD")

    def test_reject_result_leak_in_target_and_fake_flags(self):
        for kind in ("target", "contract", "score", "time"):
            payload = sample()
            if kind == "target":
                payload["target_fixture"]["home_goals"] = 5
            elif kind == "contract":
                payload["production_recommendations"] = "ENABLED"
            elif kind == "score":
                payload["historical_matches"][0]["home_goals"] = True
            else:
                payload["target_fixture"]["kickoff_utc"] = "2026-09-01T09:00:00Z"
            self.assertEqual(evaluate(payload, model_factory=FakeModel)["status"], "HOLD")

    def test_invalid_probs_not_leaked(self):
        class Bad(FakeModel):
            def predict(self, *args, **kw):
                class Grid:
                    home_draw_away = [0.9, 0.9, -0.8]
                return Grid()
        result = evaluate(sample(), model_factory=Bad)
        self.assertEqual(result["status"], "HOLD")
        self.assertNotIn("p_home", result)

    def test_same_provider_name_with_distinct_ids_supported(self):
        payload = sample()
        payload["historical_matches"][0]["source_event_display_name"] = "foo"
        self.assertEqual(evaluate(payload, model_factory=FakeModel)["status"], "HOLD")
        del payload["historical_matches"][0]["source_event_display_name"]
        self.assertEqual(evaluate(payload, model_factory=FakeModel)["status"], "RESEARCH_ONLY")

    def test_naive_time_and_invalid_result_time(self):
        for value in ("2026-10-01T09:00:00", "2026-10-01T10:00:00Z"):
            with self.subTest(value=value):
                payload = sample()
                payload["as_of_utc"] = value
                expected = "RESEARCH_ONLY" if value.endswith("Z") else "HOLD"
                self.assertEqual(evaluate(payload, model_factory=FakeModel)["status"], expected)
        payload = sample()
        payload["historical_matches"][0]["result_recorded_utc"] = payload["historical_matches"][0]["kickoff_utc"]
        self.assertEqual(evaluate(payload, model_factory=FakeModel)["status"], "HOLD")

    def test_model_fit_failure_returns_hold(self):
        class Fail(FakeModel):
            def fit(self):
                raise RuntimeError("invalid fit")
        result = evaluate(sample(), model_factory=Fail)
        self.assertEqual(result["status"], "HOLD")
        self.assertNotIn("p_home", result)

    def test_no_import_when_input_invalid(self):
        with patch.dict("sys.modules", {"penaltyblog": None}):
            payload = sample()
            payload["historical_matches"] = []
            self.assertEqual(evaluate(payload)["reason"], "INVALID_OR_UNVERIFIED_INPUT")

    def test_existing_output_and_input_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "train.json", Path(tmp) / "report.json"
            original = json.dumps(sample())
            inp.write_text(original)
            out.write_text("previous report")
            with self.assertRaises(FileExistsError):
                main(["--input", str(inp), "--output", str(out)])
            self.assertEqual(out.read_text(), "previous report")
            self.assertEqual(inp.read_text(), original)
            with self.assertRaises(ValueError):
                main(["--input", str(inp), "--output", str(inp)])

    def test_valid_output_created_private_and_not_certified(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp, out = Path(tmp) / "train.json", Path(tmp) / "report.json"
            inp.write_text(json.dumps(sample()))
            with patch.dict("sys.modules", {"penaltyblog": None}):
                result = main(["--input", str(inp), "--output", str(out)])
            self.assertEqual(result["status"], "HOLD")
            self.assertFalse(json.loads(out.read_text())["positive_ev_verified"])
            self.assertEqual(out.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
