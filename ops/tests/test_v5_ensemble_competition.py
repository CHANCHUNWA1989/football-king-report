import copy
import unittest
from datetime import date,timedelta
from ops.v5_ensemble_competition import NAMES,blend,dc,evaluate,weights

def rows():
    out=[]
    for start in (date(2025,9,1),date(2026,1,1)):
        for i in range(120):
            out.append({"league":"test","date":(start+timedelta(days=i)).isoformat(),
                        "home":"H","away":"A","y":i%3,"p":{k:[.4,.3,.3] for k in NAMES}})
    return out
class EnsembleTest(unittest.TestCase):
    def test_normalized(self):
        self.assertAlmostEqual(sum(dc(1.5,1.1)),1)
        for _,w in weights():self.assertAlmostEqual(sum(blend(rows()[0]["p"],w)),1)
    def test_assessment_does_not_choose_weights(self):
        a=rows();r=evaluate(a);b=copy.deepcopy(a)
        for x in b[120:]:x["y"]=0
        s=evaluate(b)
        self.assertEqual(r["selected_weights"],s["selected_weights"])
        self.assertEqual(r["development_best_single"],s["development_best_single"])
    def test_duplicate_and_missing_model(self):
        a=rows();a.append(a[0])
        with self.assertRaises(ValueError):evaluate(a)
        a=rows();del a[0]["p"][NAMES[0]]
        with self.assertRaises(ValueError):evaluate(a)
    def test_invalid_probability(self):
        a=rows();a[0]["p"][NAMES[0]]=[.9,.9,.9]
        with self.assertRaises(ValueError):evaluate(a)
    def test_hold_and_same_cases(self):
        self.assertEqual(evaluate(rows()[:10])["status"],"HOLD")
        r=evaluate(rows())
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual({v["n"] for v in r["assessment_metrics"].values()},{120})
        self.assertFalse(r["prospective_validation"])

    def test_leave_one_out_grid_and_nonnegative_weights(self):
        grid=dict(weights())
        for name in NAMES:
            w=grid["exclude_"+name]
            self.assertEqual(w[name],0)
            self.assertAlmostEqual(sum(w.values()),1)
            self.assertTrue(all(v>=0 for v in w.values()))
        p=rows()[0]["p"]
        bad=grid["equal"].copy()
        bad[NAMES[0]]=-.1
        bad[NAMES[1]]=1-sum(v for k,v in bad.items() if k!=NAMES[1])
        with self.assertRaises(ValueError):blend(p,bad)
        bad=grid["equal"].copy()
        bad[NAMES[0]]=True
        with self.assertRaises(ValueError):blend(p,bad)

    def test_development_only_exclusion_and_assessment_veto(self):
        a=rows()
        for r in a:
            good=[.1,.1,.1];good[r["y"]]=.8
            bad=[.495,.495,.495];bad[r["y"]]=.01
            r["p"]={name:list(bad if name==NAMES[-1] else good) for name in NAMES}
        result=evaluate(a)
        self.assertEqual(result["selected_grid_name"],"exclude_"+NAMES[-1])
        self.assertEqual(result["selected_weights"][NAMES[-1]],0)
        # Equal to the best single model is not a strict improvement.
        self.assertFalse(result["passes_retrospective_score_gate"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
        self.assertFalse(result["automatic_promotion"])
        b=copy.deepcopy(a)
        for r in b[120:]:r["y"]=(r["y"]+1)%3
        changed=evaluate(b)
        self.assertEqual(result["selected_weights"],changed["selected_weights"])

    def test_tied_models_do_not_pass_strict_gate(self):
        result=evaluate(rows())
        self.assertFalse(result["passes_retrospective_score_gate"])
        self.assertFalse(result["automatic_promotion"])
