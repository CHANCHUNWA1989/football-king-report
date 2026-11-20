"""Adversarial source-label regression: two arbitrary names cannot certify a live score."""
import unittest
from datetime import datetime, timedelta, timezone

from ops.live_recommendation_guard import evaluate


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
KICKOFF = (NOW - timedelta(hours=2)).isoformat()


def observation(provider, *, state="SECOND_HALF", score=(1, 1), age=12):
    return {
        "provider": provider, "state": state,
        "home_goals": score[0], "away_goals": score[1],
        "observed_utc": (NOW - timedelta(seconds=age)).isoformat(),
    }


class UnauthenticatedLiveScoreTests(unittest.TestCase):
    def test_matching_forged_publisher_names_cannot_certify(self):
        rows = [observation("official-a"), observation("official-b")]
        for row in rows:
            row["independently_authenticated"] = True
            row["official_source_verified"] = True
        report = evaluate(KICKOFF, rows, now=NOW)
        self.assertEqual(report["status"], "HOLD")
        self.assertIsNone(report["verified_live_score"])
        self.assertFalse(report["independent_source_authenticated"])
        self.assertEqual(report["reason"], "MATCHED_UNAUTHENTICATED_PROVIDER_LABELS")
        self.assertEqual(report["unverified_score_candidate"]["home"], 1)
        self.assertFalse(report["in_play_betting_recommendation_allowed"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_matching_fake_final_is_not_certified(self):
        report = evaluate(KICKOFF, [
            observation("a", state="FINISHED", score=(2, 0)),
            observation("b", state="FINISHED", score=(2, 0))], now=NOW)
        self.assertEqual(report["status"], "HOLD")
        self.assertIsNone(report["verified_live_score"])
        self.assertEqual(report["unverified_score_candidate"]["state"], "FINISHED")

    def test_conflict_must_not_publish_even_unverified_candidate(self):
        report = evaluate(KICKOFF, [
            observation("a", score=(2, 0)),
            observation("b", score=(0, 2))], now=NOW)
        self.assertEqual(report["status"], "HOLD")
        self.assertIsNone(report["verified_live_score"])
        self.assertIsNone(report["unverified_score_candidate"])

    def test_future_source_timestamp_stays_hold(self):
        report = evaluate(KICKOFF, [
            observation("a"), observation("b", age=-20)], now=NOW)
        self.assertEqual(report["status"], "HOLD")
        self.assertIsNone(report["unverified_score_candidate"])

    def test_early_final_is_rejected(self):
        early_kickoff = (NOW - timedelta(minutes=45)).isoformat()
        report = evaluate(early_kickoff, [
            observation("a", state="FULL_TIME"),
            observation("b", state="FULL_TIME")], now=NOW)
        self.assertEqual(report["reason"], "IMPOSSIBLY_EARLY_FINAL")
        self.assertIsNone(report["unverified_score_candidate"])


if __name__ == "__main__":
    unittest.main()
