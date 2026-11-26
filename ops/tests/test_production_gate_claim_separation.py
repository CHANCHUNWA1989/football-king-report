"""Untrusted summaries cannot satisfy formal release conditions."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from production_gate import gate


class ClaimSeparationTests(unittest.TestCase):
    def run_gate(self, interval, **extra):
        center = {"production_recommendations":"DISABLED",
                  "six_league_result_verification_complete":True,
                  "market_odds_are_executable":True,
                  "risk_adjusted_roi_and_clv_independently_verified":True,
                  **extra}
        evidence = {"production_recommendations":"DISABLED","samples":[],"n":0}
        validation = {"production_recommendations":"DISABLED",
                      "immutable_forecast_evidence_verified":True,
                      "measurements":{"difference_block_bootstrap_95pct_ci":interval}}
        return gate(center,evidence,validation)

    def test_all_formal_conditions_false_even_with_positive_claims(self):
        result=self.run_gate([.1,.3])
        self.assertTrue(all(v is False for v in result["conditions"].values()))
        self.assertEqual(result["status"],"HOLD")
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertEqual(result["authenticated_forward_samples"],0)

    def test_positive_claims_preserved_as_unverified_diagnostics(self):
        claims=self.run_gate([.1,.3])["unverified_research_claims"]
        self.assertFalse(claims["authenticated"])
        for key in ("bootstrap_interval_valid_shape","bootstrap_lower_positive",
                    "six_league_result_verification_claimed",
                    "immutable_forecast_evidence_claimed","executable_market_odds_claimed",
                    "risk_adjusted_roi_and_clv_claimed"):
            self.assertTrue(claims[key],key)

    def test_invalid_intervals_not_serialized(self):
        for ci in ([.3,.1],[float("inf"),float("inf")],[float("nan"),1],
                   [True,2],[10**1000,10**1001],[],{"lo":.1,"hi":.2}):
            with self.subTest(ci_type=type(ci).__name__):
                result=self.run_gate(ci)
                claims=result["unverified_research_claims"]
                self.assertFalse(claims["bootstrap_interval_valid_shape"])
                self.assertIsNone(claims["bootstrap_interval"])
                self.assertFalse(claims["bootstrap_lower_positive"])
                json.dumps(result,allow_nan=False)

    def test_valid_interval_crossing_zero_is_not_positive(self):
        claims=self.run_gate([-.1,.2])["unverified_research_claims"]
        self.assertTrue(claims["bootstrap_interval_valid_shape"])
        self.assertFalse(claims["bootstrap_lower_positive"])

    def test_guaranteed_roi_remains_only_a_claim(self):
        result=self.run_gate([.1,.3],guaranteed_positive_roi=True)
        self.assertTrue(result["unverified_research_claims"]["guaranteed_roi_claimed"])
        self.assertFalse(result["conditions"]["positive_risk_adjusted_roi_and_clv_independently_tested"])


if __name__=="__main__":
    unittest.main()
