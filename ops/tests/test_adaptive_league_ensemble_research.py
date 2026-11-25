import copy
import unittest
from datetime import datetime,timedelta,timezone
from ops.adaptive_league_ensemble_research import evaluate,MODELS

BASE=datetime(2025,1,1,tzinfo=timezone.utc)


def row(i,league="L",outcome="H"):
    f=BASE+timedelta(days=i)
    return {"event_id":f"{league}-{i}","league":league,
            "forecast_at":f.isoformat(),"kickoff_at":(f+timedelta(hours=2)).isoformat(),
            "settled_at":(f+timedelta(hours=4)).isoformat(),"outcome":outcome,
            "model_probabilities":{
                m:{"H":h,"D":d,"A":1-h-d} for m,h,d in
                zip(MODELS,(.4,.55,.75,.2),(.3,.2,.15,.3))}}


class AdaptiveEnsembleTests(unittest.TestCase):
    def test_history_gate_and_same_cohort(self):
        r=evaluate([row(i) for i in range(40)])
        self.assertEqual(r["paired_n"],40)
        self.assertEqual(r["adaptive_active_n"],10)
        self.assertEqual(r["weight_trace"][29]["weights"],{m:.25 for m in MODELS})
        w=r["weight_trace"][30]["weights"]
        self.assertGreater(w["dixon_coles"],w["dynamic_score_poisson"])
        self.assertAlmostEqual(sum(w.values()),1)
        self.assertTrue(all(.05<=v<=.85 for v in w.values()))
        self.assertTrue(all(v["sample_count"]==40 for v in r["diagnostics"].values()))
        self.assertLess(r["diagnostics"]["adaptive"]["log_loss"],
                        r["diagnostics"]["uniform"]["log_loss"])
        self.assertEqual(r["certified_prospective_samples"],0)
        self.assertFalse(r["production_weights_changed"])

    def test_future_outcome_cannot_change_earlier_weights(self):
        a=[row(i) for i in range(40)]
        b=copy.deepcopy(a)
        for item in b[34:]:
            item["outcome"]="A"
        self.assertEqual(evaluate(a)["weight_trace"][:35],
                         evaluate(b)["weight_trace"][:35])

    def test_same_time_result_excluded(self):
        a=[row(i) for i in range(30)]+[row(30)]
        a[29]["settled_at"]=a[30]["forecast_at"]
        r=evaluate(a)
        self.assertEqual(r["weight_trace"][-1]["prior_count"],29)
        self.assertFalse(r["weight_trace"][-1]["adaptive_active"])

    def test_league_isolation_and_order_invariance(self):
        a=[row(i) for i in range(40)]+[row(40,"OTHER")]
        r=evaluate(a)
        self.assertEqual(r,evaluate(list(reversed(a))))
        self.assertEqual(r["weight_trace"][-1]["prior_count"],0)
        self.assertEqual(r["weight_trace"][-1]["weights"],{m:.25 for m in MODELS})

    def test_all_invalid_inputs_fail_closed(self):
        for change in (
            {"model_probabilities":{}},{"outcome":"?"},{"forecast_at":"2025-01-01"},
            {"settled_at":BASE.isoformat()},{"verified":True},
        ):
            self.assertNotIn("diagnostics",evaluate([row(0)|change]))
        self.assertNotIn("diagnostics",evaluate([row(0),row(0)]))
        a=row(0)
        a["model_probabilities"]["poisson"]["H"]=True
        self.assertNotIn("diagnostics",evaluate([a]))


if __name__=="__main__":
    unittest.main()
