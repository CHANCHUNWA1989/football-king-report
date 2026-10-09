import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from global_readiness import report
from global_fixture_discovery import collect

NOW=datetime(2026,10,10,tzinfo=timezone.utc)
PAYLOAD={"data":[{"id":10,"competition":"K League 1","home":"Seoul",
                  "away":"Ulsan","kickoff":"2026-10-10T10:00:00Z"}]}

class ReadinessTests(unittest.TestCase):
    def test_no_data_means_hold_and_zero_picks(self):
        d=report(now=NOW)
        self.assertEqual(d["global_fixture_count"],0)
        self.assertEqual(d["recommendation_count"],0)
        self.assertEqual(d["production_recommendations"],"DISABLED")
        self.assertEqual(d["minimum_decimal_odds"],1.80)
        self.assertEqual(d["minimum_conservative_ev"],.03)

    def test_valid_global_coverage_is_not_a_bet(self):
        g=collect(NOW,loader=lambda url: PAYLOAD if url.endswith("10") else {"data":[]})
        d=report(g,now=NOW)
        self.assertEqual(d["global_observed_competitions"],1)
        self.assertEqual(d["global_fixture_count"],1)
        self.assertEqual(d["recommendations"],[])
        self.assertIn("NO_VALIDATED_FORWARD_POSITIVE_EV",d["blockers"])

    def test_forged_global_counts_are_rejected(self):
        g=collect(NOW,loader=lambda url: PAYLOAD if url.endswith("10") else {"data":[]})
        g["observed_competition_count"]=200
        d=report(g,now=NOW)
        self.assertFalse(d["global_discovery_validated"])
        self.assertEqual(d["global_observed_competitions"],0)

    def test_self_attested_forward_settlement_never_unlocks(self):
        g=collect(NOW,loader=lambda url: PAYLOAD if url.endswith("10") else {"data":[]})
        d=report(g,{"schema":"football-king-wide-free-leagues-v1",
                     "production_recommendations":"DISABLED"},
                 {"events":[{"id":"foo"}],"production_recommendations":"DISABLED"},
                 {"candidate_forward_samples":100000,
                  "independent_forward_samples":100000,
                  "calibration_verified":True},now=NOW)
        self.assertTrue(d["wide_audit_present"])
        self.assertTrue(d["market_audit_present"])
        self.assertEqual(d["independently_authenticated_settlements"],0)
        self.assertEqual(d["recommendation_count"],0)

    def test_fake_production_global_source_rejected(self):
        g=collect(NOW,loader=lambda url: PAYLOAD if url.endswith("10") else {"data":[]})
        g["production_recommendations"]="ENABLED"
        self.assertEqual(report(g,now=NOW)["global_fixture_count"],0)

if __name__=="__main__":
    unittest.main()
