"""Phase 11 adversarial tests for GO/HOLD and stress boundaries."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prematch_phase11_go_hold import evaluate_ev_decision, phase11_go_hold_report
from prematch_phase11_stress import run_stress
from prematch_release_gate import REQUIRED_CI


class TestPhaseEleven(unittest.TestCase):
    def test_all_green_positive_ev_cannot_authorize(self):
        market = {"status": "RESEARCH_ONLY",
                  "expected_values": {"home": .12, "draw": -.1, "away": -.05}}
        ev = evaluate_ev_decision(market, transaction_cost=.02,
                                  uncertainty=.03, independently_validated=True)
        self.assertEqual(ev["net_ev_diagnostics"]["home"], .07)
        self.assertEqual(ev["status"], "HOLD")
        self.assertIn("PRODUCTION_EV_AUTHORIZATION_UNAVAILABLE", ev["rejection_reasons"])
        report = phase11_go_hold_report(
            commit_sha="a" * 40,
            ci_conclusions={name: "success" for name in REQUIRED_CI},
            market=market, sandbox_evidence={"verified": True},
            tsa_evidence={"verified": True}, source_evidence={"verified": True},
            heldout_evidence={"passed": True})
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(len(report["report_sha256"]), 64)

    def test_invalid_risk_parameters_and_no_ev(self):
        market = {"status": "RESEARCH_ONLY",
                  "expected_values": {"home": .01, "draw": -.1, "away": -.1}}
        self.assertIn("NET_EV_BELOW_THRESHOLD",
                      evaluate_ev_decision(market)["rejection_reasons"])
        self.assertIn("INVALID_RISK_PARAMETERS",
                      evaluate_ev_decision(market, uncertainty=float("nan"))["rejection_reasons"])
        self.assertIn("INVALID_EV_ESTIMATES",
                      evaluate_ev_decision({"status": "RESEARCH_ONLY",
                                            "expected_values": {"home": True}})["rejection_reasons"])

    def test_repeatable_subprocess_stress(self):
        report = run_stress(workers=3, writes_per_worker=8, timeout_seconds=40)
        self.assertEqual(report["status"], "RESEARCH_ONLY", report)
        self.assertEqual(report["observed_writes"], 24)
        self.assertEqual(report["integrity"]["unique_archive_digests"], 24)

    def test_stress_bounds(self):
        with self.assertRaises(ValueError):
            run_stress(workers=0)
        with self.assertRaises(ValueError):
            run_stress(writes_per_worker=1000)


if __name__ == "__main__":
    unittest.main()
