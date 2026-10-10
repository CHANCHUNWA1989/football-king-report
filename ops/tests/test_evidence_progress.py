"""Evidence progress must distinguish source overlap from genuine betting evidence."""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from evidence_progress import measure, publish


class EvidenceProgressTests(unittest.TestCase):
    def setUp(self):
        self.center={
            "schema":"football-king-research-center-1",
            "production_recommendations":"DISABLED",
            "total_strict_market_pairs":38
        }
        self.gate={
            "schema":"football-king-production-qualification-1",
            "production_recommendations":"DISABLED",
            "settled_samples":1,"week_blocks":1,"qualifying_leagues":0,
            "failed_conditions":["at_least_300_settled_point_in_time_samples"]
        }
        self.scores={
            "schema":"football-king-independent-final-score-audit-v1",
            "production_recommendations":"DISABLED",
            "two_provider_exact_score_agreements":0,
            "single_source_agreements":1
        }
        self.asian={
            "schema":"football-king-asian-spread-forward-paper-audit-v1",
            "production_recommendations":"DISABLED",
            "qualified_pre_match_quote_count":0,
            "licensed_executable_prices_confirmed":False
        }
        self.now=datetime(2026,10,10,tzinfo=timezone.utc)

    def test_actual_missing_evidence_cannot_be_supplanted_by_history(self):
        result=measure(self.center,self.gate,self.scores,self.asian,now=self.now)
        self.assertEqual(result["model_market_comparable_cases"],38)
        self.assertEqual(result["settled_forward_samples"],1)
        self.assertEqual(result["remaining_forward_samples"],299)
        self.assertEqual(result["independent_exact_score_pairs_on_settled_samples"],0)
        self.assertEqual(result["asian_actual_verified_spread_quotes"],0)
        self.assertEqual(result["asian_pre_match_paper_settlements"],0)
        self.assertIn("NO_LICENSED_EXECUTABLE_ASIAN_QUOTE_AT_BET_TIME",
                      result["missing_evidence"])
        self.assertFalse(result["model_ready_for_production"])
        self.assertFalse(result["automatic_bets_allowed"])
        self.assertTrue(result["historical_simulation_not_counted_as_forward_validation"])
        self.assertEqual(result["production_recommendations"],"DISABLED")

    def test_even_two_source_score_and_paper_quote_never_autounlocks(self):
        self.scores["two_provider_exact_score_agreements"]=50
        self.asian["qualified_pre_match_quote_count"]=120
        self.gate.update(settled_samples=350,week_blocks=18,qualifying_leagues=4)
        result=measure(self.center,self.gate,self.scores,self.asian,now=self.now)
        self.assertEqual(result["remaining_forward_samples"],0)
        self.assertEqual(result["remaining_week_blocks"],0)
        self.assertFalse(result["positive_ev_betting_confirmed"])
        self.assertFalse(result["model_ready_for_production"])
        self.assertFalse(result["automatic_bets_allowed"])

    def test_two_publisher_score_correlations_never_replace_certification(self):
        self.gate["settled_samples"] = 6
        self.scores["bundesliga_two_publisher_candidate_audit"] = {
            "status": "CANDIDATE_CORRELATION_ONLY",
            "two_publisher_ft_candidate_fixtures": 29,
            "settled_outcomes_correlated": 4,
            "settled_outcome_conflicts": 1,
            "results_cryptographically_attested": False,
            "forward_predictions_independently_validated": False,
        }
        result = measure(self.center, self.gate, self.scores, self.asian, now=self.now)
        self.assertEqual(result["two_publisher_bundesliga_outcome_correlations_research_only"], 4)
        self.assertEqual(result["two_publisher_bundesliga_outcome_conflicts_research_only"], 1)
        self.assertEqual(result["independent_exact_score_pairs_on_settled_samples"], 0)
        self.assertIn("NO_EXACT_TWO_PUBLISHER_SETTLED_FT_RESULT", result["missing_evidence"])
        self.assertFalse(result["model_ready_for_production"])
        self.scores["bundesliga_two_publisher_candidate_audit"]["settled_outcomes_correlated"] = 9999
        unsafe = measure(self.center, self.gate, self.scores, self.asian, now=self.now)
        self.assertEqual(unsafe["two_publisher_bundesliga_outcome_correlations_research_only"], 0)

    def test_missing_or_malicious_documents_default_hold(self):
        d=measure({},{"production_recommendations":"ENABLED"},None,None,now=self.now)
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["remaining_forward_samples"],300)
        self.assertIn("NO_VERIFIED_PRODUCTION_GATE_REPORT",d["missing_evidence"])
        self.assertFalse(d["positive_ev_betting_confirmed"])

    def test_diagnostic_publish_requires_no_external_provider(self):
        with tempfile.TemporaryDirectory() as root:
            d=publish(root)
            output=json.loads((Path(root)/"evidence_progress.json").read_text())
            self.assertEqual(d["schema"],output["schema"])
            self.assertEqual(output["production_recommendations"],"DISABLED")
            self.assertEqual(output["settled_forward_samples"],0)


if __name__=="__main__":
    unittest.main()
