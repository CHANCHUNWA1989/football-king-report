"""Synthetic-only tests for chronological split and score reconstruction."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_halftime_study import extract,evaluate


def example():
    match={"match_id":1,"home_team":{"home_team_id":10},"away_team":{"away_team_id":20},
           "competition_stage":{"name":"Group Stage"},"match_status":"available",
           "match_date":"2022-11-20","home_score":2,"away_score":1}
    def shot(i,period,team,xg,outcome):
        return {"id":str(i),"index":i,"period":period,"type":{"name":"Shot"},
                "team":{"id":team},"player":{"id":team*10},"shot":{"statsbomb_xg":xg,"outcome":{"name":outcome}}}
    events=[shot(1,1,10,.4,"Goal"),shot(2,1,10,.3,"Goal"),
            {"id":"3","index":3,"period":1,"type":{"name":"Half End"}},
            shot(4,2,20,.2,"Goal"),shot(5,2,10,.1,"Saved"),
            {"id":"6","index":6,"period":2,"type":{"name":"Half End"}}]
    return match,events


def cohort():
    return [{"match_id":i+1,"day":"2022-11-21" if i<32 else "2022-11-30",
             "home_ht":2,"away_ht":0,"home_first_xg":1.0,
             "home_second_xg":.5 if i<32 else .8,
             "away_first_xg":.4,"away_second_xg":.6} for i in range(48)]


class HalftimeStudyTests(unittest.TestCase):
    def test_reconcile_full_time_and_halftime(self):
        m,e=example()
        r=extract(json.dumps(e).encode(),m)
        self.assertEqual((r["home_ht"],r["away_ht"]),(2,0))
        self.assertAlmostEqual(r["home_first_xg"],.7)
        self.assertAlmostEqual(r["home_second_xg"],.1)
        m["home_score"]=3
        with self.assertRaises(ValueError):
            extract(json.dumps(e).encode(),m)

    def test_own_goal_for_counted_only_once(self):
        m,e=example()
        e[1]={"id":"2","index":2,"period":1,"type":{"name":"Own Goal For"},"team":{"id":10}}
        r=extract(json.dumps(e).encode(),m)
        self.assertEqual(r["home_ht"],2)
        self.assertAlmostEqual(r["home_first_xg"],.4)

    def test_chronological_split_and_no_holdout_fitting(self):
        rows=cohort()
        a=evaluate(rows)
        self.assertTrue(a["fit_performed"])
        self.assertAlmostEqual(a["private_metrics"]["train_pooled_ratio"],.5)
        self.assertAlmostEqual(a["private_metrics"]["holdout_mse_fixed_085"],.0025)
        for r in rows[32:]:
            r["home_second_xg"]=2
        b=evaluate(rows)
        self.assertEqual(a["private_metrics"]["train_pooled_ratio"],b["private_metrics"]["train_pooled_ratio"])
        self.assertEqual(b["true_forward_sample_count"],0)
        self.assertFalse(b["model_accuracy_verified"])
        self.assertEqual(b["production_recommendations"],"DISABLED")

    def test_insufficient_leaders_and_duplicate_match_fail_closed(self):
        rows=cohort()
        for r in rows:
            r["home_ht"]=1
        self.assertIsNone(evaluate(rows)["private_metrics"])
        rows=cohort()
        rows[1]["match_id"]=rows[0]["match_id"]
        self.assertEqual(evaluate(rows)["reason"],"INVALID_HISTORICAL_COHORT")
        self.assertEqual(evaluate(rows[:47])["reason"],"INCOMPLETE_PREDECLARED_GROUP_STAGE")
