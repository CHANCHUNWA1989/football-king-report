"""Event-time replay regression for interleaving forecast/kickoff clocks."""
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from ops.research_walkforward_v1 import Match,walk_forward
from ops.research_team_ratings_v1 import Fixture,walk_forward_teams
from ops.research_result_clock import event_time_batches

BASE=datetime(2026,11,1,12,tzinfo=timezone.utc)
MODELS=((Match,walk_forward,"mean_metrics"),(Fixture,walk_forward_teams,"metrics"))
def fixture(cls,fid,ko,forecast,h,a,goals=1):
    k=BASE+timedelta(hours=ko); f=BASE+timedelta(hours=forecast)
    if cls is Match:return Match(k,goals,0,True,k+timedelta(hours=2),fid,f)
    return Fixture(k,h,a,goals,0,True,k+timedelta(hours=2),fid,f)
def rows(cls,goals,cutoff):
    return [fixture(cls,"a",0,-1,"a","b",goals),
            fixture(cls,"b",3,-2,"c","d"),
            fixture(cls,"c",6,cutoff,"a","e")]
class EventTimeReplayTests(unittest.TestCase):
    def test_reorders_by_original_forecast(self):
        for cls,fn,_ in MODELS:
            r=fn(rows(cls,0,1),warmup=2,event_time_order=True)
            self.assertEqual(r["evaluation_order"],"FORECAST_UTC")
            self.assertEqual(r["n_test"],1)
            self.assertEqual(r["results_applied_before_last_forecast"],0)
            self.assertFalse(r["forecast_clock_authenticated"])
    def test_delayed_result_cannot_leak(self):
        for cls,fn,field in MODELS:
            for cutoff in (1,2):
                a=fn(rows(cls,0,cutoff),warmup=2,event_time_order=True)
                b=fn(rows(cls,5,cutoff),warmup=2,event_time_order=True)
                self.assertEqual(a[field],b[field])
            a=fn(rows(cls,0,3),warmup=2,event_time_order=True)
            b=fn(rows(cls,5,3),warmup=2,event_time_order=True)
            self.assertNotEqual(a[field],b[field])
            self.assertEqual(a["results_applied_before_last_forecast"],1)
    def test_kickoff_group_closure_and_permutation(self):
        for cls,fn,_ in MODELS:
            a=fixture(cls,"a",0,-4,"a","b")
            b=fixture(cls,"b",0,-2,"c","d")
            x=fixture(cls,"x",3,-3,"e","f")
            y=fixture(cls,"y",6,1,"a","g")
            r=fn([a,b,x,y],warmup=1,event_time_order=True)
            self.assertEqual(r,fn([b,a,x,y],warmup=1,event_time_order=True))
            self.assertEqual(r["effective_warmup"],3)
            self.assertEqual(r["n_test"],1)
    def test_equal_forecast_group_closure(self):
        for cls,fn,_ in MODELS:
            a,b,c=rows(cls,0,1);b=replace(b,forecast_utc=a.forecast_utc)
            r=fn([a,b,c],warmup=1,event_time_order=True)
            self.assertEqual(r["effective_warmup"],2)
    def test_missing_ids_or_clocks_rejected(self):
        for cls,fn,_ in MODELS:
            a,b,c=rows(cls,0,1)
            for bad in (replace(a,fixture_id=None),replace(a,forecast_utc=None)):
                with self.assertRaises(ValueError):fn([bad,b,c],warmup=1,event_time_order=True)
    def test_no_whole_group_after_warmup(self):
        for cls,fn,_ in MODELS:
            a=fixture(cls,"a",0,-4,"a","b")
            b=fixture(cls,"b",0,-2,"c","d")
            x=fixture(cls,"x",3,-3,"e","f")
            with self.assertRaises(ValueError):fn([a,b,x],warmup=1,event_time_order=True)
