"""Regression for result look-ahead in overlapping matches."""
import unittest
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from ops.research_walkforward_v1 import Match,walk_forward
from ops.research_team_ratings_v1 import Fixture,walk_forward_teams
from ops.research_result_clock import ResultClock

BASE=datetime(2026,11,1,12,tzinfo=timezone.utc)
def records(cls,first_goals,delay_minutes=120):
    k=BASE+timedelta(minutes=60)
    if cls is Match:
        return [Match(BASE,first_goals,0,True,BASE+timedelta(minutes=delay_minutes)),
                Match(k,1,0,True,k+timedelta(hours=2))]
    return [Fixture(BASE,"a","b",first_goals,0,True,BASE+timedelta(minutes=delay_minutes)),
            Fixture(k,"a","c",1,0,True,k+timedelta(hours=2))]
class ResultAvailabilityTests(unittest.TestCase):
    def test_overlap_gas(self):
        a=walk_forward(records(Match,0),warmup=1)
        b=walk_forward(records(Match,5),warmup=1)
        self.assertEqual(a["mean_metrics"],b["mean_metrics"])
        self.assertEqual(a["results_applied_before_last_kickoff"],0)
    def test_overlap_team(self):
        a=walk_forward_teams(records(Fixture,0),warmup=1)
        b=walk_forward_teams(records(Fixture,5),warmup=1)
        self.assertEqual(a["metrics"],b["metrics"])
        self.assertEqual(a["results_applied_before_last_kickoff"],0)
    def test_known_result_changes_later_prediction(self):
        for cls,fn,field in ((Match,walk_forward,"mean_metrics"),(Fixture,walk_forward_teams,"metrics")):
            outputs=[]
            for goals in (0,5):
                a,b=records(cls,goals)
                if cls is Match:b=replace(b,kickoff_utc=BASE+timedelta(hours=3),result_available_utc=BASE+timedelta(hours=5))
                else:b=replace(b,kickoff=BASE+timedelta(hours=3),result_available_utc=BASE+timedelta(hours=5))
                r=fn([a,b],warmup=1)
                self.assertEqual(r["results_applied_before_last_kickoff"],1)
                outputs.append(r[field])
            self.assertNotEqual(*outputs)
    def test_missing_and_impossible_result_clock(self):
        for cls,fn in ((Match,walk_forward),(Fixture,walk_forward_teams)):
            a,b=records(cls,0)
            for value in (None,BASE+timedelta(minutes=89),datetime(2026,11,1,14)):
                with self.assertRaises(ValueError):fn([replace(a,result_available_utc=value),b],warmup=1)
    def test_availability_order_and_equal_clock(self):
        c=ResultClock();applied=[]
        c.schedule(BASE+timedelta(hours=3),"late")
        c.schedule(BASE+timedelta(hours=2),"first")
        c.schedule(BASE+timedelta(hours=2),"second")
        c.drain_before(BASE+timedelta(hours=2),applied.append)
        self.assertEqual(applied,[])
        c.drain_before(BASE+timedelta(hours=3),applied.append)
        self.assertEqual(applied,["first","second"])
        c.drain_before(BASE+timedelta(hours=4),applied.append)
        self.assertEqual(applied,["first","second","late"])
