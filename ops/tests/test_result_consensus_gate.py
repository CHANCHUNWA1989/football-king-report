"""Caller-authored observations may establish agreement, never authentication."""
import unittest

from result_consensus_gate import verify_result


KICKOFF = "2026-10-12T12:00:00Z"


def observation(provider="publisher-a", group="claimed-a", **changes):
    row = {"fixture_id": "f1", "status": "FT", "provider_id": provider,
           "independent_group_id": group, "published_utc": "2026-10-12T15:00:00Z",
           "home_goals": 2, "away_goals": 1,
           "source_url": "https://example.org/fixture/f1", "raw_sha256": "a" * 64}
    row.update(changes)
    return row


class ResultConsensusGateTests(unittest.TestCase):
    def test_caller_groups_hashes_and_flags_cannot_authenticate(self):
        rows = [observation("publisher-a", "claimed-a"),
                observation("publisher-b", "claimed-b")]
        for row in rows:
            row.update(result_verified=True, independently_verified=True,
                       source_identity_independently_authenticated=True,
                       outcomes_independently_authenticated=True,
                       eligible_for_model_scoring=True)
        verdict = verify_result("f1", KICKOFF, rows)
        self.assertEqual(verdict["status"], "AGREED_UNVERIFIED")
        self.assertEqual(verdict["result"], [2, 1])
        self.assertFalse(verdict["independently_verified"])
        self.assertFalse(verdict["result_verified"])
        self.assertFalse(verdict["eligible_for_model_scoring"])

    def test_consistent_claims_are_preserved_with_authentication_flags_false(self):
        verdict = verify_result("f1", KICKOFF, [observation(), observation("b", "b")])
        self.assertEqual(verdict["status"], "AGREED_UNVERIFIED")
        self.assertEqual(verdict["source_ids"], ["b", "publisher-a"])
        self.assertEqual(verdict["claimed_group_ids"], ["b", "claimed-a"])
        self.assertEqual(verdict["latest_observed_utc"], "2026-10-12T15:00:00+00:00")
        for flag in ("raw_provenance_rechecked", "source_identity_independently_authenticated",
                     "source_independence_authenticated", "fixture_identity_authenticated",
                     "actual_kickoff_authenticated", "completion_authenticated",
                     "period_authenticated", "eligible_for_betting_promotion"):
            self.assertIs(verdict[flag], False, flag)
        self.assertEqual(verdict["production_recommendations"], "DISABLED")

    def test_shared_group_is_consistent_but_never_independent(self):
        verdict = verify_result("f1", KICKOFF,
                                [observation("a", "shared"), observation("b", "shared")])
        self.assertEqual(verdict["status"], "AGREED_UNVERIFIED")
        self.assertEqual(verdict["claimed_group_ids"], ["shared"])
        self.assertIs(verdict["source_independence_authenticated"], False)

    def test_same_provider_cannot_become_two_claims_by_changing_group(self):
        verdict = verify_result("f1", KICKOFF,
                                [observation("a", "one"), observation("a", "two")])
        self.assertEqual(verdict["status"], "HOLD")
        self.assertEqual(verdict["reason"], "SOURCE_PROVENANCE_CONFLICT")
        self.assertIsNone(verdict["result"])

    def test_duplicate_provider_is_not_two_sources(self):
        verdict = verify_result("f1", KICKOFF, [observation(), observation()])
        self.assertEqual(verdict["status"], "HOLD")
        self.assertEqual(verdict["source_ids"], ["publisher-a"])

    def test_conflicting_scores_fail_closed_for_all_group_arrangements(self):
        for provider, group in [("publisher-a", "claimed-a"),
                                ("b", "claimed-a"), ("b", "other")]:
            with self.subTest(provider=provider, group=group):
                verdict = verify_result("f1", KICKOFF,
                                        [observation(), observation(provider, group, home_goals=0)])
                self.assertEqual(verdict["status"], "HOLD")
                self.assertEqual(verdict["reason"], "SOURCE_CONFLICT")
                self.assertIsNone(verdict["result"])

    def test_other_fixture_non_finished_and_invalid_scores_are_not_agreement(self):
        for changes in ({"fixture_id": "other"}, {"status": "LIVE"},
                        {"home_goals": True}, {"away_goals": -1},
                        {"home_goals": 31}, {"home_goals": 2.0}):
            with self.subTest(changes=changes):
                verdict = verify_result("f1", KICKOFF,
                                        [observation(), observation("b", "b", **changes)])
                self.assertEqual(verdict["status"], "HOLD")

    def test_invalid_or_early_publication_cannot_claim_completed_regulation(self):
        for stamp in ("2026-10-12T11:59:00Z", "2026-10-12T13:29:59Z",
                      "2026-10-12T15:00:00", "broken", None):
            with self.subTest(stamp=stamp):
                verdict = verify_result("f1", KICKOFF,
                                        [observation(), observation("b", "b", published_utc=stamp)])
                self.assertEqual(verdict["status"], "HOLD")

    def test_claimed_kickoff_mismatch_is_excluded(self):
        for key in ("kickoff_utc", "publisher_kickoff_utc"):
            verdict = verify_result("f1", KICKOFF,
                                    [observation(), observation("b", "b", **{key: "2026-10-13T12:00:00Z"})])
            self.assertEqual(verdict["status"], "HOLD")

    def test_explicit_extra_time_or_penalties_are_not_regulation_agreement(self):
        for key in ("result_period", "score_period", "period"):
            for period in ("EXTRA_TIME", "PENALTIES", "HALF_TIME", "UNKNOWN", None):
                with self.subTest(key=key, period=period):
                    verdict = verify_result("f1", KICKOFF,
                                            [observation(), observation("b", "b", **{key: period})])
                    self.assertEqual(verdict["status"], "HOLD")

    def test_explicit_regulation_and_matching_clock_are_still_unverified(self):
        rows = [observation(result_period="REGULATION_90_MINUTES"),
                observation("b", "b", period="REGULATION_90_MINUTES",
                            publisher_kickoff_utc="2026-10-12T14:00:00+02:00")]
        verdict = verify_result("f1", KICKOFF, rows)
        self.assertEqual(verdict["status"], "AGREED_UNVERIFIED")
        self.assertIs(verdict["period_authenticated"], False)
        self.assertIs(verdict["actual_kickoff_authenticated"], False)

    def test_invalid_input_is_hold(self):
        for fixture, kickoff, rows in [(True, KICKOFF, []), ("f1", "bad", []),
                                       ("f1", KICKOFF, {}), ("", KICKOFF, [])]:
            verdict = verify_result(fixture, kickoff, rows)
            self.assertEqual(verdict["status"], "HOLD")
            self.assertEqual(verdict["reason"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
