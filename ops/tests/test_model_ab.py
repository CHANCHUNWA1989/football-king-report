"""Research-only A/B candidate is fixed pre-result, no data leakage."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model_ab import candidate,apply,MODEL


class ABLifecycleTests(unittest.TestCase):
    def test_conservative_candidate_is_normalized(self):
        x=candidate([.7,.2,.1])
        self.assertAlmostEqual(sum(x),1,places=5)
        self.assertTrue(x[0]<.7)

    def test_even_baseline_remains_even(self):
        x=candidate([1/3]*3)
        self.assertAlmostEqual(x[0],1/3,places=5)

    def test_no_results_or_odds_used(self):
        s={"as_of_utc":"2026-10-09T04:00:00+00:00",
           "production_recommendations":"DISABLED",
           "predictions":[{"p_home":.4,"p_draw":.25,"p_away":.35,
                           "prediction_utc":"2026-10-09T04:00:00+00:00",
                           "production_recommendations":"DISABLED"}]}
        res=apply(s)
        self.assertFalse(res["promotion_allowed"])
        self.assertEqual(res["candidate_model"],MODEL)
        self.assertNotIn("score_ft",s["predictions"][0])
        self.assertEqual(s["predictions"][0]["prediction_utc"],"2026-10-09T04:00:00+00:00")

    def test_invalid_probability_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"INVALID_BASELINE"):
            candidate([.95,.95,-.90])

    def test_unsafe_flag_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNSAFE_SHADOW_INPUT"):
            apply({"production_recommendations":"ENABLED","predictions":[]})


if __name__=="__main__":
    unittest.main()
