"""Zero-network regression tests for fail-closed Japanese live status triage."""
import unittest

from jleague_japanese_status_gate import triage


BASE = {
    "source_event_id": "synthetic-j1-20261121-kyoto-urawa",
    "source_updated_utc": "2026-11-21T05:15:00Z",
    "captured_utc": "2026-11-21T05:16:00Z",
    "as_of_utc": "2026-11-21T05:17:00Z",
}


class JapaneseJ1StatusGateTests(unittest.TestCase):
    def triage(self, label, **overrides):
        args = {**BASE, **overrides}
        return triage(label, **args)

    def assert_research_only_without_certification(self, result):
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["model_scoring_eligible"])
        self.assertFalse(result["independently_authenticated"])
        self.assertFalse(result["settlement_certified"])
        self.assertFalse(result["positive_ev_certified"])
        self.assertNotIn("score_home", result)
        self.assertNotIn("score_away", result)

    def test_first_half_minute_is_unverified_single_source(self):
        result = self.triage("前半7分")
        self.assert_research_only_without_certification(result)
        self.assertEqual(result["match_status"], "FIRST_HALF")
        self.assertEqual(result["period_minute"], 7)

    def test_second_half_minute_is_unverified_single_source(self):
        result = self.triage("後半14分")
        self.assert_research_only_without_certification(result)
        self.assertEqual(result["match_status"], "SECOND_HALF")
        self.assertEqual(result["period_minute"], 14)

    def test_prematch_is_hold_and_never_exposes_score(self):
        result = self.triage("試合前")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "PREMATCH_NOT_LIVE")
        self.assertEqual(result["match_status"], "NOT_STARTED")
        self.assertNotIn("score_home", result)

    def test_generic_match_in_progress_without_minute_is_hold(self):
        result = self.triage("試合中")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "STATUS_REQUIRES_MORE_EVIDENCE")

    def test_finished_or_half_time_not_certified(self):
        for label in ("試合終了", "ハーフタイム", "前半終了"):
            with self.subTest(label=label):
                self.assertEqual(self.triage(label)["status"], "HOLD")

    def test_unknown_or_malformed_label_is_hold(self):
        for label in ("0-0", "前半45+2分", "前半0分", "前半71分", "試合中 0-0", " 試合中"):
            with self.subTest(label=label):
                self.assertEqual(self.triage(label)["status"], "HOLD")

    def test_stale_upstream_update_does_not_become_fresh_by_capture(self):
        result = self.triage("前半7分", source_updated_utc="2026-11-21T05:04:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "STALE_OR_FUTURE_SOURCE_TIME")

    def test_future_updated_time_fails_closed(self):
        result = self.triage("前半7分", source_updated_utc="2026-11-21T05:20:00Z")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "STALE_OR_FUTURE_SOURCE_TIME")

    def test_missing_fixture_event_id_fails_closed(self):
        result = self.triage("前半7分", source_event_id="")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "MISSING_SOURCE_EVENT_ID")

    def test_naive_clock_fails_closed(self):
        result = self.triage("前半7分", as_of_utc="2026-11-21T05:17:00")
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "NAIVE_TIMESTAMP")


if __name__ == "__main__":
    unittest.main()
