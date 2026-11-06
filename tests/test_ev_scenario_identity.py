"""Synthetic, fail-closed identity and pre-match timing checks for model scenarios."""
import unittest
from datetime import datetime, timezone, timedelta
from ops.all_market_screen import screen

NOW = datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)
P = {"full_win": .4, "half_win": .2, "push": 0, "half_loss": .1, "full_loss": .3}

def fixture():
    return {
        "fixture_id": "synthetic-event-1", "market": "asian_handicap",
        "selection": "away", "line": 1.25, "decimal_odds": 2.1,
        "source": "synthetic-book", "observed_utc": "2026-10-10T09:58:00Z",
        "captured_utc": "2026-10-10T09:59:00Z",
        "kickoff_utc": "2026-10-10T12:00:00Z",
        "settlement_probabilities": dict(P),
    }

def scenario(name):
    return {
        "model_id": name,
        "fixture_id": "synthetic-event-1", "market": "asian_handicap",
        "selection": "away", "line": "1.25",
        "kickoff_utc": "2026-10-10T20:00:00+08:00",
        "forecast_created_utc": "2026-10-10T09:55:00Z",
        "settlement_probabilities": dict(P),
    }

def run(quote):
    return screen({"quotes": [quote]}, NOW)["candidates"][0]


class TestModelScenarioIdentity(unittest.TestCase):
    def test_good_exact_contract_keeps_uncertified_sensitivity(self):
        q = fixture()
        q["model_scenarios"] = [scenario("a"), scenario("b")]
        row = run(q)
        self.assertEqual(row["status"], "RESEARCH_ONLY")
        self.assertAlmostEqual(row["scenario_ev_min"], .2)
        self.assertFalse(row["positive_ev_verified"])
        self.assertFalse(row["model_independence_verified"])

    def test_wrong_event_market_selection_line_and_kickoff_rejected(self):
        wrong = {
            "fixture_id": "another-event",
            "market": "totals",
            "selection": "home",
            "line": -1.25,
            "kickoff_utc": "2026-10-10T12:15:00Z",
        }
        for field, value in wrong.items():
            with self.subTest(field=field):
                q = fixture()
                a, b = scenario("a"), scenario("b")
                b[field] = value
                q["model_scenarios"] = [a, b]
                row = run(q)
                self.assertEqual(row["status"], "INVALID")
                self.assertEqual(row["reason"], "INVALID_MODEL_SCENARIOS")
                self.assertNotIn("ev_per_unit", row)

    def test_missing_identity_field_is_rejected(self):
        for field in ("fixture_id", "market", "selection", "line",
                      "kickoff_utc", "forecast_created_utc"):
            with self.subTest(field=field):
                q = fixture()
                a, b = scenario("a"), scenario("b")
                b.pop(field)
                q["model_scenarios"] = [a, b]
                row = run(q)
                self.assertEqual(row["status"], "INVALID")
                self.assertNotIn("scenario_ev_min", row)

    def test_forecast_timestamp_must_precede_source_quote(self):
        for bad in ("2026-10-10T09:58:00Z", "2026-10-10T09:59:00Z",
                    "2026-10-10T12:00:00Z", "2026-10-10T09:50:00",
                    "bad-time", None, True):
            with self.subTest(bad=bad):
                q = fixture()
                a, b = scenario("a"), scenario("b")
                b["forecast_created_utc"] = bad
                q["model_scenarios"] = [a, b]
                row = run(q)
                self.assertEqual(row["status"], "INVALID")
                self.assertNotIn("ev_per_unit", row)

    def test_equivalent_numeric_quarter_lines_accepted(self):
        q = fixture()
        a, b = scenario("a"), scenario("b")
        a["line"], b["line"] = 1.25, "1.250"
        q["model_scenarios"] = [a, b]
        self.assertEqual(run(q)["status"], "RESEARCH_ONLY")

    def test_invalid_signed_line_and_bools_rejected(self):
        for bad in (True, None, 1.2, float("nan"), "-1.25"):
            with self.subTest(bad=bad):
                q = fixture()
                a, b = scenario("a"), scenario("b")
                b["line"] = bad
                q["model_scenarios"] = [a, b]
                self.assertEqual(run(q)["reason"], "INVALID_MODEL_SCENARIOS")

    def test_one_bound_scenario_is_still_insufficient(self):
        q = fixture()
        q["model_scenarios"] = [scenario("a")]
        row = run(q)
        self.assertEqual(row["ev_sensitivity_status"], "INSUFFICIENT_SCENARIOS")
        self.assertNotIn("scenario_ev_min", row)
        self.assertFalse(row["positive_ev_verified"])


if __name__ == "__main__":
    unittest.main()
