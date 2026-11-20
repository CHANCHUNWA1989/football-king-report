"""Provider adapter regression and adversarial identity/timestamp checks."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_provider_adapter import normalize_provider_snapshot


class TestPrematchProviderAdapter(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "provider_id": "provider-a", "provider_fixture_id": "abc-456",
            "home_team_id": "team-1", "away_team_id": "team-2",
            "kickoff_at_utc": "2026-10-24T12:00:00Z",
            "captured_at_utc": "2026-10-24T11:00:00Z",
            "decimal_odds": {"home": 2.0, "draw": 3.5, "away": 4.0}}
        self.fixture = {
            "fixture_id": "match-123", "home_team_id": "team-1",
            "away_team_id": "team-2",
            "kickoff_at_utc": "2026-10-24T12:00:00Z"}
        self.probs = {"home": 0.55, "draw": 0.25, "away": 0.20}

    def run_adapter(self, payload=None, fixture=None, **kwargs):
        return normalize_provider_snapshot(
            self.payload if payload is None else payload,
            self.fixture if fixture is None else fixture,
            evaluated_at_utc=kwargs.pop("evaluated_at_utc", "2026-10-24T11:05:00Z"),
            model_version="v1", model_probabilities=self.probs, **kwargs)

    def test_valid_payload_stays_research_only(self):
        result = self.run_adapter()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["fixture_id"], "match-123")
        self.assertEqual(result["provider_fixture_id"], "abc-456")
        self.assertAlmostEqual(result["expected_values"]["home"], 0.1)
        self.assertFalse(result["provider_identity_verified"])
        self.assertFalse(result["capture_timestamp_attested"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_team_swap_and_fixture_mismatch_hold(self):
        for key, value in (("home_team_id", "team-2"),
                           ("away_team_id", "team-1"),
                           ("home_team_id", " TEAM-1 "),
                           ("provider_fixture_id", "")):
            with self.subTest(key=key, value=value):
                payload = copy.deepcopy(self.payload)
                payload[key] = value
                self.assertEqual(self.run_adapter(payload=payload)["status"], "HOLD")

    def test_kickoff_discrepancies_hold(self):
        for value in ("2026-10-24T12:01:01Z", "2026-10-24T11:58:59Z", "bad"):
            payload = copy.deepcopy(self.payload)
            payload["kickoff_at_utc"] = value
            self.assertEqual(self.run_adapter(payload=payload)["status"], "HOLD")

    def test_future_stale_and_post_kickoff_hold(self):
        for captured, evaluated in (
            ("2026-10-24T11:06:00Z", "2026-10-24T11:05:00Z"),
            ("2026-10-24T10:00:00Z", "2026-10-24T11:05:00Z"),
            ("2026-10-24T12:00:00Z", "2026-10-24T12:01:00Z")):
            payload = copy.deepcopy(self.payload)
            payload["captured_at_utc"] = captured
            self.assertEqual(self.run_adapter(payload=payload,
                             evaluated_at_utc=evaluated)["status"], "HOLD")

    def test_invalid_provider_quote_holds(self):
        for odds in ({"home": 2.0, "draw": 3.5},
                     {"home": 1.0, "draw": 3.5, "away": 4.0}):
            payload = copy.deepcopy(self.payload)
            payload["decimal_odds"] = odds
            self.assertEqual(self.run_adapter(payload=payload)["status"], "HOLD")

    def test_invalid_matching_tolerance_holds(self):
        for tolerance in (True, -1, 301, 0.5):
            self.assertEqual(self.run_adapter(
                max_kickoff_delta_seconds=tolerance)["status"], "HOLD")

    def test_within_tolerance_remains_research_only(self):
        payload = copy.deepcopy(self.payload)
        payload["kickoff_at_utc"] = "2026-10-24T12:00:45Z"
        self.assertEqual(self.run_adapter(payload=payload)["status"], "RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
