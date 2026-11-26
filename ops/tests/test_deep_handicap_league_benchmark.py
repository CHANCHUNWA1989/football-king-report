"""Synthetic full-season and leakage checks."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_league_benchmark import parse,fit,rates,evaluate,grade_distributions


def season():
    # Balanced cyclic orientation: each team has 9 or 10 home games.
    teams=list(range(1,21))
    pairs=[]
    for k in range(19):
        for i in range(10):
            h,a=teams[i],teams[-i-1]
            diff=(a-h)%20
            if diff>10 or (diff==10 and h>a):
                h,a=a,h
            pairs.append((h,a))
        teams=[teams[0],teams[-1],*teams[1:-1]]
    rows=[]
    for i,(h,a) in enumerate(pairs+[(a,h) for h,a in pairs]):
        rows.append({"match_id":i+1,"home_team":{"home_team_id":h},"away_team":{"away_team_id":a},
                     "match_date":"2015-12-01" if i<190 else "2016-02-01",
                     "competition":{"competition_id":2},"season":{"season_id":27},
                     "match_status":"available","competition_stage":{"name":"Regular Season"},
                     "home_score":2,"away_score":1})
    return rows


class LeagueBenchmarkTests(unittest.TestCase):
    def test_full_cohort_and_neutral_equal_models(self):
        r=evaluate(season(),2)
        self.assertEqual(r["evaluated_count"],190)
        self.assertEqual(r["true_forward_sample_count"],0)
        self.assertFalse(r["actual_market_lines_available"])
        for values in r["private_metrics"].values():
            self.assertAlmostEqual(values["brier_delta"],0)
            self.assertAlmostEqual(values["log_delta"],0)

    def test_holdout_does_not_change_model(self):
        rows=season()
        train,test=parse(rows,2)
        model=fit(train)
        for r in rows[190:]:
            r["home_score"]=8
            r["away_score"]=0
        train2,_=parse(rows,2)
        self.assertEqual(model,fit(train2))
        self.assertEqual(rates(model,test[0][2],test[0][3]),
                         rates(fit(train2),test[0][2],test[0][3]))

    def test_duplicate_incomplete_and_wrong_season_blocked(self):
        for action in (lambda r:r.pop(),lambda r:r.__setitem__(1,copy.deepcopy(r[0])),
                       lambda r:r[0]["season"].update(season_id=28),
                       lambda r:r[0].update(home_score=True)):
            rows=season()
            action(rows)
            self.assertIsNone(evaluate(rows,2)["private_metrics"])

    def test_grade_mass(self):
        for p in grade_distributions(2.9,.9,"HOME").values():
            self.assertAlmostEqual(sum(p.values()),1)
