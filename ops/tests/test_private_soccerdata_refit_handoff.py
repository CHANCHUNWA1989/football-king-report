import unittest
from unittest.mock import patch
from ops.private_soccerdata_refit_handoff import refit_verified_history, refit_unverified_research


class HandoffTests(unittest.TestCase):
    def test_unverified_history_cannot_be_promoted(self):
        with self.assertRaisesRegex(ValueError, "ATTESTATION_REQUIRED"):
            refit_verified_history({"schema": "football-king-private-utc-history-v1",
                "production_recommendations": "DISABLED",
                "source_attestation_verified": False,
                "result_availability_attested": False}, [])

    def test_self_asserted_attestation_not_accepted(self):
        with self.assertRaisesRegex(ValueError, "NOT_IMPLEMENTED"):
            refit_verified_history({"schema": "football-king-private-utc-history-v1",
                "production_recommendations": "DISABLED",
                "source_attestation_verified": True,
                "result_availability_attested": True}, [])

    def test_local_timestamp_history_cannot_be_refit(self):
        with self.assertRaisesRegex(ValueError, "EXPLICIT_UTC_HISTORY_REQUIRED"):
            refit_unverified_research([{"source_local_match_datetime": "2026-01-01T12:00:00"}], [])

    @patch("ops.private_soccerdata_refit_handoff.refit_walkforward")
    def test_explicit_utc_rows_call_existing_model(self, refit):
        refit.return_value = {"production_recommendations": "DISABLED",
                              "independent_provenance_verified": False,
                              "positive_ev_verified": False, "status": "HOLD"}
        row = dict.fromkeys(("source_namespace", "event_id", "league_id",
            "home_team_id", "away_team_id", "kickoff_utc", "result_recorded_utc",
            "home_goals", "away_goals"))
        result = refit_unverified_research([row], [])
        self.assertEqual(result["status"], "HOLD")
        refit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
