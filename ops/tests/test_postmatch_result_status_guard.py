"""Regression: never misread abandoned 4-0 as normal FT; keep 39 abstentions."""
import json
import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postmatch_result_status_guard import reconcile_two_published_results


def pair():
    base = {
        "league": "eredivisie", "home": "Cambuur",
        "away": "Go Ahead Eagles",
        "kickoff_utc": "2026-10-31T20:00:00Z",
        "home_goals": 4, "away_goals": 0, "match_status": "FT",
    }
    a = dict(base, publisher="Score+90",
             source_url="https://scoreplus90.com/en/matches/2026-10-31")
    b = dict(base, publisher="LiveScore",
             source_url="https://www.livescore.mobi/football/holland/")
    return [a, b]


class PostmatchResultStatusGuardTests(unittest.TestCase):
    def test_two_distinct_regular_full_time_sources_only_research(self):
        r = reconcile_two_published_results(pair())
        self.assertEqual(r["status"], "RESEARCH_ONLY")
        self.assertTrue(r["score_agreement"])
        self.assertFalse(r["upstream_independence_certified"])
        self.assertFalse(r["bookmaker_settlement_eligible"])
        self.assertFalse(r["model_scoring_eligible"])

    def test_one_source_abandoned_other_claims_ft_is_hold(self):
        rows = pair()
        rows[1]["match_status"] = "ABANDONED"
        r = reconcile_two_published_results(rows)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"], "ABANDONED_OR_SUSPENDED_REQUIRES_OFFICIAL_DECISION")

    def test_both_sources_abandoned_is_still_hold(self):
        rows = pair()
        for r in rows:
            r["match_status"] = "ABANDONED"
        self.assertEqual(reconcile_two_published_results(rows)["status"], "HOLD")

    def test_disagreeing_scores_hold(self):
        rows = pair()
        rows[1]["away_goals"] = 1
        self.assertEqual(reconcile_two_published_results(rows)["reason"], "CROSS_SOURCE_SCORE_CONFLICT")

    def test_mismatched_fixture_identity_hold(self):
        rows = pair()
        rows[1]["home"] = "Manchester City"
        self.assertEqual(reconcile_two_published_results(rows)["reason"], "FIXTURE_IDENTITY_CONFLICT")

    def test_duplicate_source_host_hold(self):
        rows = pair()
        rows[1]["source_url"] = "https://scoreplus90.com/en/matches/2026-10-31"
        self.assertEqual(reconcile_two_published_results(rows)["reason"], "DUPLICATE_SOURCE")

    def test_boolean_score_rejected(self):
        rows = pair()
        rows[1]["home_goals"] = True
        self.assertEqual(reconcile_two_published_results(rows)["reason"], "INVALID_SCORE")

    def test_non_https_rejected(self):
        rows = pair()
        rows[1]["source_url"] = "http://www.livescore.mobi/football/holland/"
        self.assertEqual(reconcile_two_published_results(rows)["reason"], "INVALID_SOURCE_URL")

    def test_malformed_url_port_rejected_without_crash(self):
        rows = pair()
        rows[1]["source_url"] = "https://www.livescore.mobi:invalid/football/holland/"
        self.assertEqual(reconcile_two_published_results(rows)["reason"], "INVALID_SOURCE_URL")

    def test_checked_in_43_results_do_not_promote_model_or_rewrite_seal(self):
        path = (Path(__file__).resolve().parents[2] / "research" / "audits"
                / "2026-10-31-hk-evening-43-postmatch-research-only.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data["events"]
        self.assertEqual(len(rows), 43)
        self.assertEqual(sum(x["original_direction"] is None for x in rows), 39)
        self.assertEqual(sum(x["original_direction"] is not None for x in rows), 4)
        self.assertEqual(sum(x["source_fixture_id_sealed"] is None for x in rows), 20)
        self.assertEqual(sum(x["result_status"] == "REGULATION_FT" for x in rows), 42)
        self.assertEqual(data["production_recommendations"], "DISABLED")
        self.assertIsNone(data["roi"])
        self.assertIsNone(data["ev"])
        self.assertIsNone(data["brier"])
        self.assertEqual(data["original_blob_sha"], "a100c234c326e26fefa9b0fd96a65427c1b9ce63")
        self.assertEqual(data["initial_seal_commit_sha"], "870f9d8cf5515cd004602b57d339fb7b48f1eda5")
        self.assertEqual(data["initial_seal_blob_sha"], "49c4fb6bfd735f292a767376eae309eb0afaa019")
        expected = {
            "20261031-005": ("FULL_WIN", (0, 1)),
            "20261031-006": ("FULL_LOSS", (2, 0)),
            "20261031-013": ("PUSH", (2, 2)),
            "20261031-015": ("FULL_WIN", (2, 1)),
        }
        for row in rows:
            self.assertFalse(row["market_settlement_eligible"])
            self.assertFalse(row["score_settlement_eligible_for_model"])
            self.assertIsNone(row["observed_executable_price"])
            self.assertIsNone(row["roi"])
            self.assertIsNone(row["ev"])
            self.assertIsNone(row["brier"])
            self.assertEqual(len(row["independent_publishers_checked"]), 2)
            if row["case_id"] in expected:
                outcome, score = expected[row["case_id"]]
                self.assertEqual(row["qualitative_outcome"], outcome)
                self.assertEqual((row["score"]["home"], row["score"]["away"]), score)
            else:
                self.assertIsNone(row["qualitative_outcome"])
        interrupted = rows[31]
        self.assertEqual(interrupted["case_id"], "20261031-032")
        self.assertEqual(interrupted["result_status"], "OFFICIAL_AWARDED_AFTER_ABANDONMENT")
        self.assertTrue(interrupted["additional_authority_url"].startswith("https://www.knvb.nl/"))


if __name__ == "__main__":
    unittest.main()
