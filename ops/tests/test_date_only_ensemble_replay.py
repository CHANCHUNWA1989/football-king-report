import unittest
from datetime import date,timedelta
from ops.date_only_ensemble_replay import evaluate_date_fusion, MODELS
from ops.dynamic_2026_date_split_audit import evaluate
from ops.tests.test_bivariate_real_2026_paired_oos import rows,FakePackage


def fixture(n=40):
    days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(n)]
    vectors={m:[{"HOME":h,"DRAW":.1,"AWAY":.9-h} for _ in days]
             for m,h in zip(MODELS,(.4,.5,.7,.2))}
    return days,vectors,["HOME"]*n


class DateOnlyFusionTests(unittest.TestCase):
    def test_gap_and_active_cohort(self):
        days,v,y=fixture()
        r=evaluate_date_fusion(days,v,y)
        self.assertEqual(r["weight_trace"][30]["prior_count"],29)
        self.assertEqual(r["weight_trace"][31]["prior_count"],30)
        self.assertEqual(r["adaptive_active_n"],9)
        self.assertEqual(r["active_cohort"]["adaptive"]["sample_count"],9)
        self.assertLess(r["active_cohort"]["adaptive"]["log_loss"],
                        r["active_cohort"]["uniform"]["log_loss"])
        self.assertFalse(r["production_weights_changed"])
        self.assertEqual(r["certified_prospective_samples"],0)

    def test_same_and_previous_day_outcomes_do_not_change_weights(self):
        days,v,y=fixture()
        original=evaluate_date_fusion(days,v,y)
        y[30]="AWAY"
        new=evaluate_date_fusion(days,v,y)
        self.assertEqual(original["weight_trace"][:32],new["weight_trace"][:32])
        self.assertNotEqual(original["weight_trace"][32],new["weight_trace"][32])

    def test_same_date_batch(self):
        days,v,y=fixture()
        days[32]=days[31]
        r=evaluate_date_fusion(days,v,y)
        self.assertEqual(r["weight_trace"][31]["weights"],r["weight_trace"][32]["weights"])

    def test_invalid_probability_and_missing_model(self):
        days,v,y=fixture()
        v["poisson"][0]["HOME"]=True
        with self.assertRaises(ValueError):
            evaluate_date_fusion(days,v,y)
        days,v,y=fixture()
        v.pop("poisson")
        with self.assertRaises(ValueError):
            evaluate_date_fusion(days,v,y)

    def test_existing_replay_integrated_without_new_training(self):
        train,heldout=rows()
        r=evaluate(train,heldout,model_module=FakePackage,min_train=30,min_test=5)
        fusion=r["date_only_ensemble_replay"]
        self.assertEqual(fusion["paired_n"],8)
        self.assertIsNone(fusion["active_cohort"])
        self.assertEqual(fusion["all_cohort"]["adaptive"],fusion["all_cohort"]["uniform"])
        self.assertFalse(r["test_scores_passed_to_model_fit"])


if __name__=="__main__":
    unittest.main()
