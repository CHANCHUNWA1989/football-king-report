import copy
import math
import unittest
from ops.dynamic_score_driven_poisson import score_grid, MIN_RATE, MAX_RATE
from ops.reused_model_triage import evaluate, PIN, SCHEMA, MODELS, CLASSES


def synthetic():
    scores = {}
    for model in MODELS:
        scores[model] = {}
        for market, classes in CLASSES.items():
            scores[model][market] = {
                "n":186, "mean_brier":.6 if model=="dynamic_score_poisson" else .5,
                "mean_logloss":1.1 if model=="dynamic_score_poisson" else 1.,
                "observed_class_counts":{k:186 if i==0 else 0 for i,k in enumerate(classes)},
                "mean_forecast_class_probability":{k:1/len(classes) for k in classes}}
    return {"schema":SCHEMA,"source_sha256":PIN,"status":"HOLD",
            "reason":"EXPLORATORY_REUSED_2026_RESULTS_NOT_CERTIFIED_FORWARD_TEST",
            "production_recommendations":"DISABLED","tested_models":list(MODELS),
            "training_real_matches":260,"source_test_rows":186,
            "same_eligible_heldout_games":186,"certified_prospective_samples":0,
            "bootstrap_draws":2000,
            **{k:False for k in ("positive_ev_verified","model_promoted",
                "original_holdout_untouched_confirmatory","independently_timestamped_prematch_vectors",
                "test_scores_passed_to_model_fit","real_quote_prices_verified")},
            "per_model_scores":scores,
            "dynamic_minus_dixon_coles_paired_date_cluster_CI95":{
                market:{metric:{"mean_delta":.1,"distinct_date_clusters":41,
                                "interval_95pct":[.01,.2],"includes_zero":False}
                        for metric in ("brier","logloss")} for market in CLASSES}}


class ReusedModelTriageTests(unittest.TestCase):
    def test_deprioritize_never_promotes(self):
        out=evaluate(synthetic())
        self.assertEqual(set(out["research_triage"].values()),{"DEPRIORITIZE_ON_REUSED_COHORT"})
        self.assertFalse(out["production_weights_changed"])
        self.assertEqual(out["certified_prospective_samples"],0)
        self.assertEqual(out["production_recommendations"],"DISABLED")

    def test_uncertain_and_small_cluster(self):
        r=synthetic()
        r["dynamic_minus_dixon_coles_paired_date_cluster_CI95"]["1X2"]["brier"].update(
            interval_95pct=[-.1,.2],includes_zero=True)
        r["dynamic_minus_dixon_coles_paired_date_cluster_CI95"]["OVER_2.5"]["logloss"]["distinct_date_clusters"]=29
        out=evaluate(r)["research_triage"]
        for market in ("1X2","OVER_2.5"):
            self.assertEqual(out[market],"INCONCLUSIVE_KEEP_RESEARCH_ONLY")

    def test_forged_or_incomplete_report(self):
        for k,v in (("source_sha256","0"*64),("model_promoted",True),
                    ("certified_prospective_samples",True),("source_test_rows",185)):
            self.assertFalse(evaluate(synthetic()|{k:v})["research_triage"])
        r=synthetic()
        r["per_model_scores"]["original_A"].pop("1X2")
        self.assertFalse(evaluate(r)["research_triage"])

    def test_inconsistent_metric_and_counts(self):
        for field,value in (("mean_brier",float("nan")),("mean_brier",.8),
                            ("n",185),("mean_forecast_class_probability",{})):
            r=synthetic()
            r["per_model_scores"]["dynamic_score_poisson"]["1X2"][field]=value
            self.assertFalse(evaluate(r)["research_triage"])
        r=synthetic()
        counts=r["per_model_scores"]["original_A"]["1X2"]["observed_class_counts"]
        keys=list(counts)
        counts[keys[0]]-=1
        counts[keys[1]]+=1
        self.assertFalse(evaluate(r)["research_triage"])


class DynamicRateStressTests(unittest.TestCase):
    def test_rate_grid_mass_symmetry_and_order(self):
        rates=[MIN_RATE,.1,.25,.5,1.,1.5,2.,3.,4.,5.,6.,MAX_RATE]
        for h in rates:
            for a in rates:
                with self.subTest(h=h,a=a):
                    r=score_grid(h,a)
                    p=r["p_home_draw_away"]
                    self.assertAlmostEqual(sum(p),1,places=9)
                    self.assertTrue(all(math.isfinite(x) and 0<=x<=1 for x in p))
                    rev=score_grid(a,h)["p_home_draw_away"]
                    for x,y in zip(p,reversed(rev)):
                        self.assertAlmostEqual(x,y,places=9)
                    for section in ("over_total_goals_settlement","home_asian_handicap_settlement"):
                        for grades in r[section].values():
                            self.assertAlmostEqual(sum(grades.values()),1,places=8)
                            self.assertTrue(all(math.isfinite(x) and 0<=x<=1 for x in grades.values()))
                    overs=r["over_total_goals_settlement"]
                    self.assertAlmostEqual(overs["2.5"]["full_win"],overs["2.75"]["full_win"]+overs["2.75"]["half_win"],places=8)
                    self.assertAlmostEqual(overs["2.75"]["half_win"],overs["3.0"]["push"],places=8)

    def test_invalid_rates(self):
        for x in (True,None,-1,0,MAX_RATE+.001,MIN_RATE-.001,float("nan"),float("inf")):
            with self.subTest(x=x),self.assertRaises(ValueError):
                score_grid(x,1.)


if __name__=="__main__":
    unittest.main()
