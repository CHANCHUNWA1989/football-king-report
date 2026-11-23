"""Real, manually sourced J.LEAGUE J3 FT research observation.

Do not mistake this postmatch public page reference for a pre-kickoff sealed
forecast or an independently authenticated provider/original-content replay.
"""
import json
import unittest
from pathlib import Path

from ops.j3_postmatch_reference import examine

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "research/audits/2026-11-15-j3-shiga-osaka-official-ft-research.json"


def evidence():
    return json.loads(RECORD.read_text(encoding="utf-8"))


class ShigaOsakaOfficialFTResearchTests(unittest.TestCase):
    def test_public_official_ft_reference_is_real_and_direction_lost(self):
        row = evidence()
        out = examine(row)
        self.assertEqual(out["official_source_url"],
                         "https://www.jleague.jp/en/match/j3/2026/111516/")
        self.assertEqual(out["fixture_id"], "jleague-j3-2026-111516")
        self.assertEqual(out["kickoff_utc"], "2026-11-15T09:03:00+00:00")
        self.assertEqual(out["score_ft_official_page_claim"], [1, 1])
        self.assertEqual(out["match_status_from_public_page"], "FT")
        self.assertEqual(out["original_research_direction"], "AWAY")
        self.assertEqual(out["qualitative_direction_result"], "FULL_LOSS")
        self.assertEqual(out["status"], "HOLD")
        self.assertFalse(out["raw_official_source_bytes_archived"])
        self.assertFalse(out["independent_source_ft_authenticated"])
        self.assertFalse(out["pre_kickoff_model_snapshot_authenticated"])
        self.assertFalse(out["executable_bookmaker_odds_verified"])
        self.assertFalse(out["ev_verified"])
        self.assertIsNone(out["actual_bet_profit"])
        self.assertIsNone(out["calibrated_away_win_probability"])
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_modified_source_identity_status_or_fixture_is_rejected(self):
        base = evidence()
        for key, value in [
            ("source_url", "https://www.jleague.jp.evil.com/en/match/j3/2026/111516/"),
            ("source_url", "https://www.jleague.jp/en/match/j3/2026/111515/"),
            ("league", "j1"),
            ("season", "2025"),
            ("event_id", "jleague-j3-2026-111515"),
            ("home_id", "fc-osaka"),
            ("away_id", "reilac-shiga"),
            ("kickoff_utc", "2026-11-15T09:00:00+00:00"),
            ("match_status", "LIVE"),
            ("home_goals", 2),
            ("away_goals", 0),
            ("research_direction", "HOME"),
        ]:
            row = {**base, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                examine(row)

    def test_any_forged_certification_or_real_profit_is_rejected(self):
        base = evidence()
        for key, value in [
            ("source_raw_bytes_archived", True),
            ("independent_result_verified", True),
            ("forecast_sealed_before_kickoff", True),
            ("reference_price_executable", True),
            ("actual_bet_profit", 0),
            ("positive_ev_verified", True),
        ]:
            row = {**base, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                examine(row)

    def test_only_one_upstream_not_two_source_certification(self):
        row = evidence()
        self.assertEqual(row["source_publisher"], "J.LEAGUE")
        self.assertEqual(row["source_url"],
                         "https://www.jleague.jp/en/match/j3/2026/111516/")
        # A second club page on the same J.LEAGUE origin is not an
        # independently verified second upstream or a ciphertext attestation.
        self.assertEqual(examine(row)["source_independence"], "NOT_ESTABLISHED")

    def test_postmatch_ft_observation_is_not_prematch_training_evidence(self):
        row = evidence()
        result = examine(row)
        self.assertEqual(result["archive_admission"], "DENIED_POSTMATCH_UNSEALED")
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertFalse(result["eligible_for_venue_split_training"])
        self.assertFalse(result["validated_positive_ev"])


if __name__ == "__main__":
    unittest.main()
