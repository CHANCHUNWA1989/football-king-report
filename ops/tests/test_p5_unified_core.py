"""P5 cross-module safety smoke tests; synthetic and offline only."""
import unittest

from ops.tests.test_chat_postmatch_research_audit import pick
from ops.tests.test_v5_home_calibration import evidence
from ops.tests.test_nonlinear_availability_research import scenario, replace
from ops.tests.test_v5_live_xg_comeback import S, B, P, X, NOW
from ops.tests.test_v5_ensemble_competition import rows
from ops.chat_postmatch_research_audit import audit
from ops.v5_home_calibration import build
from ops.nonlinear_availability_research import evaluate as availability
from ops.v5_live_xg_comeback import predict
from ops.v5_ensemble_competition import evaluate as competition


class P5UnifiedCoreTests(unittest.TestCase):
    def test_five_modules_never_enable_production(self):
        recap = pick("synthetic", "1x2", "DRAW", None, [1, 1])
        recap["claimed_action"] = "RESEARCH_ONLY"
        reports = [audit([recap]), build(evidence()), availability(scenario()),
                   predict(S, B, P, X, now=NOW), competition(rows())]
        for report in reports:
            self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertEqual(reports[0]["formal_bet_count"], 0)
        self.assertEqual(reports[0]["certified_forward_samples"], 0)
        self.assertFalse(reports[1]["prospective_validation"])
        self.assertFalse(reports[2]["real_player_effect_verified"])
        self.assertFalse(reports[3]["actual_xg_verified"])
        self.assertFalse(reports[4]["automatic_promotion"])

    def test_synthetic_availability_output_is_not_a_live_prior_or_evidence(self):
        s = scenario()
        replace(s, "home", 1, [.3, .4])
        out = availability(s)
        self.assertEqual(out["certified_forward_samples"], 0)
        self.assertIsNone(predict(S, B, out, X, now=NOW)["distribution"])
        self.assertFalse(out["official_lineup_authenticated"])
        with self.assertRaises(ValueError):
            build(out)

    def test_regression_veto_and_unsealed_recap_cannot_supply_ensemble_cases(self):
        e = evidence()
        for r in e["samples"][60:]:
            r["y"] = 0
        rejected = build(e)
        self.assertEqual(rejected["status"], "HOLD")
        self.assertIsNone(rejected["training_model"])
        recap = audit([pick("synthetic", "1x2", "HOME", None, [2, 0])])
        self.assertFalse(recap["can_enter_formal_settlement_ledger"])
        # Ensemble schema requires complete same-case model vectors and labels.
        for report in (recap, rejected):
            with self.assertRaises((ValueError, TypeError, KeyError)):
                competition([report])
        self.assertFalse(competition(rows())["passes_retrospective_score_gate"])


if __name__ == "__main__":
    unittest.main()
