"""Offline synthetic tests: a qualitative slate is not a calibrated model."""
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tonight_slate_lock import SCHEMA, validate, classify, main


def valid_slate():
    return {
        "schema": SCHEMA, "status": "RESEARCH_ONLY",
        "production_recommendations": "DISABLED",
        "official_model_predictions": 0,
        "independently_calibrated_probabilities": False,
        "executable_prices_verified": False,
        "sealed_research_as_of_utc": "2026-10-31T13:45:00Z",
        "events": [{
            "case_id": "oct31-epl-001", "league": "epl",
            "home": "Manchester City", "away": "Brighton",
            "kickoff_utc": "2026-10-31T15:00:00Z",
            "source_fixture_id": "oddstorm:13620052",
            "fixture_source_url": "https://www.oddstorm.com/odds/match/13620052-manchester-city-vs-brighton",
            "research_direction": {
                "basis": "assistant_unpriced_hypothesis_not_model",
                "market": "asian_handicap", "side": "away", "line": 1,
                "observed_decimal_price": None, "model_probability": None,
                "certified_positive_ev": False,
                "production_recommendations": "DISABLED",
            }
        }]
    }


class ResearchAuditTests(unittest.TestCase):
    def test_valid_slate_still_has_no_certified_predictions(self):
        r = validate(valid_slate())
        self.assertEqual(r["unpriced_research_directions"], 1)
        self.assertEqual(r["independently_certified_forward_cases"], 0)
        self.assertEqual(r["production_recommendations"], "DISABLED")
        self.assertIsNone(r["roi"])

    def test_no_price_abstention_not_cherry_picked(self):
        r = valid_slate()
        a = deepcopy(r["events"][0])
        a["case_id"] = "oct31-epl-002"
        a["away"] = "Leeds"
        a["source_fixture_id"] = None
        a["research_direction"] = None
        r["events"].append(a)
        summary = validate(r)
        self.assertEqual(summary["fixtures_recorded"], 2)
        self.assertEqual(summary["abstentions_recorded"], 1)
        self.assertEqual(summary["provider_ids_missing"], 1)

    def test_late_kickoff_hard_rejection(self):
        r = valid_slate()
        r["events"][0]["kickoff_utc"] = "2026-10-31T13:50:00Z"
        with self.assertRaisesRegex(ValueError, "LATE_OR_INPLAY"):
            validate(r)

    def test_duplicate_fixture_rejected(self):
        r = valid_slate()
        a = deepcopy(r["events"][0])
        a["case_id"] = "second-case"
        r["events"].append(a)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_FIXTURE"):
            validate(r)

    def test_laundered_quote_and_prob_rejected(self):
        for key, value in (("observed_decimal_price", 1.85),
                           ("model_probability", 0.6),
                           ("certified_positive_ev", True)):
            with self.subTest(key=key):
                r = valid_slate()
                r["events"][0]["research_direction"][key] = value
                with self.assertRaises(ValueError):
                    validate(r)

    def test_spoofed_provider_id_rejected(self):
        r = valid_slate()
        r["events"][0]["source_fixture_id"] = "invented:123"
        with self.assertRaises(ValueError):
            validate(r)

    def test_cross_match_provider_url_rejected(self):
        r = valid_slate()
        r["events"][0]["source_fixture_id"] = "oddstorm:13620049"
        with self.assertRaisesRegex(ValueError, "PROVIDER_ID_SOURCE_URL_MISMATCH"):
            validate(r)

    def test_research_pick_requires_provider_id(self):
        r = valid_slate()
        r["events"][0]["source_fixture_id"] = None
        r["events"][0]["fixture_source_url"] = "https://www.livescore.mobi/football/2026-10-31/"
        with self.assertRaisesRegex(ValueError, "DIRECTION_WITHOUT_PROVIDER_ID"):
            validate(r)

    def test_missing_provider_id_restricts_schedule_origin(self):
        r = valid_slate()
        r["events"][0]["source_fixture_id"] = None
        r["events"][0]["research_direction"] = None
        r["events"][0]["fixture_source_url"] = "https://arbitrary.example/other-match"
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_FIXTURE_SOURCE"):
            validate(r)

    def test_boolean_quarter_line_rejected(self):
        r = valid_slate()
        r["events"][0]["research_direction"]["line"] = True
        with self.assertRaises(ValueError):
            validate(r)

    def test_ah_away_plus_one_push_when_loses_one(self):
        d = {"market": "asian_handicap", "side": "away", "line": 1}
        self.assertEqual(classify(d, 2, 1), "PUSH")

    def test_ah_away_plus_one_quarter_half_win_when_loses_one(self):
        d = {"market": "asian_handicap", "side": "away", "line": 1.25}
        self.assertEqual(classify(d, 2, 1), "HALF_WIN")

    def test_ah_home_minus_quarter_draw_half_loss(self):
        d = {"market": "asian_handicap", "side": "home", "line": -.25}
        self.assertEqual(classify(d, 1, 1), "HALF_LOSS")

    def test_ah_away_plus_three_quarters_loses_one_half_loss(self):
        d = {"market": "asian_handicap", "side": "away", "line": .75}
        self.assertEqual(classify(d, 2, 1), "HALF_LOSS")

    def test_total_four_under_push_at_four(self):
        d = {"market": "totals", "side": "under", "line": 4}
        self.assertEqual(classify(d, 3, 1), "PUSH")

    def test_total_over_two_quarter_two_goals_half_loss(self):
        d = {"market": "totals", "side": "over", "line": 2.25}
        self.assertEqual(classify(d, 1, 1), "HALF_LOSS")

    def test_total_under_two_quarter_two_goals_half_win(self):
        d = {"market": "totals", "side": "under", "line": 2.25}
        self.assertEqual(classify(d, 1, 1), "HALF_WIN")

    def test_total_over_two_three_quarters_three_goals_half_win(self):
        d = {"market": "totals", "side": "over", "line": 2.75}
        self.assertEqual(classify(d, 2, 1), "HALF_WIN")

    def test_total_under_two_three_quarters_three_goals_half_loss(self):
        d = {"market": "totals", "side": "under", "line": 2.75}
        self.assertEqual(classify(d, 2, 1), "HALF_LOSS")

    def test_invalid_score_and_line_rejected(self):
        d = {"market": "totals", "side": "under", "line": 2.3}
        with self.assertRaises(ValueError):
            classify(d, 2, 1)
        d["line"] = 2.25
        with self.assertRaises(ValueError):
            classify(d, True, 1)

    def test_cli_hold_on_invalid_input(self):
        with tempfile.TemporaryDirectory() as folder:
            f = Path(folder) / "data.json"
            f.write_text("{bad", encoding="utf-8")
            out = StringIO()
            with redirect_stdout(out):
                status = main(["--input", str(f)])
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
