"""No-network synthetic tests for six-league archival sample backlog and blockers."""
import gzip
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from forward_cohort_backlog import audit, publish, render
from forward_validation import extend
from model_ab import MODEL as B_MODEL, candidate as make_b
from model_market_challenger import MODEL as C_MODEL, candidate as make_c


class ForwardCohortBacklogTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 11, 16, tzinfo=timezone.utc)
        self.kickoff = self.now - timedelta(hours=4)
        self.future = self.now + timedelta(days=1)
        self.model = [0.65, 0.20, 0.15]
        self.market = [0.48, 0.28, 0.24]
        self.report = {
            "checked_utc": self.now.isoformat(),
            "production_recommendations": "DISABLED",
            "fixtures": {"matches": []},
        }
        self.record = {
            "league": "epl", "home": "Everton", "away": "Arsenal",
            "kickoff_utc": self.kickoff.isoformat(),
            "prediction_utc": (self.kickoff-timedelta(days=1)).isoformat(),
            "market_snapshot_utc": (self.kickoff-timedelta(days=1,minutes=10)).isoformat(),
            "market_updated_utc": (self.kickoff-timedelta(days=1,minutes=12)).isoformat(),
            "model": self.model, "market": self.market,
            "ab": make_b(self.model), "ab_model": B_MODEL,
            "c": make_c(self.model, self.market), "c_model": C_MODEL,
            "c_uses_only_prior_de_vigged_market": True,
            "c_research_only_not_calibrated_or_executable": True,
            "production_recommendations": "DISABLED",
        }
        self.key = ("epl", "everton", "arsenal", self.kickoff.isoformat())
        self.archived = [(self.key, self.record)]
        self.empty = {
            "schema": "football-king-forward-research-1",
            "checked_utc": self.now.isoformat(),
            "samples": [], "n": 0,
            "results_independently_verified": False,
            "profitability_verified": False,
            "production_recommendations": "DISABLED",
        }
        self.fixture = {
            "league": "epl", "home": "Everton", "away": "Arsenal",
            "kickoff_utc": self.kickoff.isoformat(), "score_ft": [1, 2],
            "status": "FINISHED",
        }

    def test_missing_result_and_future_are_distinct_unpromoted_buckets(self):
        future = {
            **self.record,
            "league": "bundesliga", "home": "Bayern", "away": "Dortmund",
            "kickoff_utc": self.future.isoformat(),
            "prediction_utc": (self.future-timedelta(days=1)).isoformat(),
            "market_snapshot_utc": (self.future-timedelta(days=1,minutes=10)).isoformat(),
        }
        archived = self.archived + [
            (("bundesliga", "bayern", "dortmund", self.future.isoformat()), future)
        ]
        result = audit(archived, self.empty, self.report)
        self.assertEqual(result["archived_distinct_pre_match_pairs"], 2)
        self.assertEqual(result["settled_forward_cases"], 0)
        self.assertEqual(result["unmatched_finished_result_backlog"], 1)
        self.assertEqual(result["score_observed_pending_settlement"], 0)
        epl, _, bundesliga = result["by_league"][:3]
        self.assertEqual(epl["score_unavailable_or_unmatched"], 1)
        self.assertEqual(bundesliga["pending_kickoff_or_two_hour_window"], 1)
        self.assertEqual(result["sealed_c_pair_count"], 2)
        self.assertEqual(result["sealed_same_case_a_b_c_market_pairs"], 2)
        self.assertEqual(result["certified_independent_settlement_cases"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_single_finished_score_audited_before_and_after_settlement(self):
        self.report["fixtures"]["matches"].append(self.fixture)
        pending = audit(self.archived, self.empty, self.report)
        self.assertEqual(pending["score_observed_pending_settlement"], 1)
        self.assertEqual(pending["settled_forward_cases"], 0)
        result = extend({}, self.archived, self.report)
        audited = audit(self.archived, result, self.report)
        self.assertEqual(audited["settled_forward_cases"], 1)
        self.assertEqual(audited["score_observed_pending_settlement"], 0)
        self.assertEqual(audited["by_league"][0]["settled_fourway_cases"], 1)
        self.assertEqual(audited["by_league"][0]["settled_c_cases"], 1)
        self.assertEqual(audited["by_league"][0]["remaining_to_40_settled"], 39)
        self.assertEqual(audited["certified_independent_settlement_cases"], 0)

    def test_conflicting_final_scores_never_credited_as_settled(self):
        self.report["fixtures"]["matches"] = [
            self.fixture, {**self.fixture, "score_ft": [2, 0]}
        ]
        audited = audit(self.archived, self.empty, self.report)
        self.assertEqual(audited["ambiguous_finished_result_backlog"], 1)
        self.assertEqual(audited["score_observed_pending_settlement"], 0)
        self.assertEqual(audited["settled_forward_cases"], 0)

    def test_time_mismatched_result_cannot_fill_backlog(self):
        self.report["fixtures"]["matches"] = [
            {**self.fixture,
             "kickoff_utc": (self.kickoff+timedelta(hours=2)).isoformat()}
        ]
        self.assertEqual(
            audit(self.archived, self.empty, self.report)["unmatched_finished_result_backlog"],
            1)

    def test_invalid_ledger_never_counts_as_forward_evidence(self):
        forged = dict(self.record)
        forged["key"] = json.dumps(self.key)
        forged["p"] = [0.9, 0.9, -0.8]
        forged["m"] = self.market
        forged["y"] = 0
        forged["forecast_utc"] = forged["prediction_utc"]
        forged["market_utc"] = forged["market_snapshot_utc"]
        forged["fixture_result_source_independently_verified"] = False
        data = {**self.empty, "samples": [forged], "n": 1}
        with self.assertRaisesRegex(ValueError, "INVALID_OR_DUPLICATE_SETTLED_EVIDENCE"):
            audit(self.archived, data, self.report)

    def test_bad_claims_and_duplicate_archive_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ARCHIVE_PAIR"):
            audit(self.archived * 2, self.empty, self.report)
        self.empty["results_independently_verified"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_COHORT_AUDIT_INPUT"):
            audit(self.archived, self.empty, self.report)

    def test_malicious_or_stale_source_results_cannot_certify_a_score(self):
        bad = {
            "schema": "football-king-single-source-finished-results-1",
            "captured_utc": self.now.isoformat(),
            "records": [self.fixture],
            "independently_verified_all_leagues": True,
            "production_recommendations": "DISABLED",
        }
        with self.assertRaisesRegex(ValueError, "INVALID_FINISHED_SOURCE_PROVENANCE"):
            audit(self.archived, self.empty, self.report, bad)

    def test_public_html_and_json_have_no_betting_authorization(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            site = root/"site"
            site.mkdir()
            (site/"report.json").write_text(json.dumps(self.report),encoding="utf-8")
            (site/"index.html").write_text(
                '<html><main><h2>近期賽程與賽果</h2></main></html>',encoding="utf-8")
            prior = root/"settled.json"
            prior.write_text(json.dumps(self.empty),encoding="utf-8")
            archive = root/"archive"
            archive.mkdir()
            with gzip.open(archive/"record.json.gz","wt",encoding="utf-8") as out:
                json.dump({"production_recommendations":"DISABLED",
                           "comparisons":[self.record]},out)
            report = publish(site,prior,archive)
            self.assertEqual(report["archived_distinct_pre_match_pairs"],1)
            self.assertEqual(report["settled_forward_cases"],0)
            doc=json.loads((site/"forward_cohort_backlog.json").read_text())
            self.assertEqual(doc["production_recommendations"],"DISABLED")
            self.assertEqual(doc["recommendations_authorized"],0)
            page=(site/"index.html").read_text()
            self.assertIn('id="forward-cohort-backlog"',page)
            self.assertIn("初步結算",page)
            self.assertNotIn("positive_ev_bets",page)
            with self.assertRaisesRegex(ValueError, "DUPLICATE_FORWARD_COHORT_SECTION"):
                publish(site,prior,archive)


if __name__ == "__main__":
    unittest.main()
