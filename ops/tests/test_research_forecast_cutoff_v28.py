"""Regression for outcomes known before kickoff but after original forecast."""
import unittest
from datetime import datetime,timedelta,timezone
from dataclasses import replace
from ops.research_walkforward_v1 import Match,walk_forward
from ops.research_team_ratings_v1 import Fixture,walk_forward_teams
from ops.tests.test_research_same_kickoff_v27 import roster

BASE=datetime(2026,11,1,12,tzinfo=timezone.utc)
def pair(cls,goals,cutoff_minutes):
    k=BASE+timedelta(hours=3)
    a_at=BASE-timedelta(minutes=10);b_at=BASE+timedelta(minutes=cutoff_minutes)
    if cls is Match:
        return [Match(BASE,goals,0,True,BASE+timedelta(hours=2),"one",a_at),
                Match(k,1,0,True,k+timedelta(hours=2),"two",b_at)]
    return [Fixture(BASE,"a","b",goals,0,True,BASE+timedelta(hours=2),"one",a_at),
            Fixture(k,"a","c",1,0,True,k+timedelta(hours=2),"two",b_at)]

MODELS=((Match,walk_forward,"mean_metrics"),(Fixture,walk_forward_teams,"metrics"))
class ForecastCutoffTests(unittest.TestCase):
    def test_between_forecast_and_kickoff(self):
        for cls,fn,field in MODELS:
            for minutes in (119,120):
                a=fn(pair(cls,0,minutes),warmup=1,require_explicit_forecast=True)
                b=fn(pair(cls,5,minutes),warmup=1,require_explicit_forecast=True)
                self.assertEqual(a[field],b[field])
                self.assertEqual(a["results_applied_before_last_forecast"],0)
    def test_known_before_forecast(self):
        for cls,fn,field in MODELS:
            a=fn(pair(cls,0,121),warmup=1,require_explicit_forecast=True)
            b=fn(pair(cls,5,121),warmup=1,require_explicit_forecast=True)
            self.assertNotEqual(a[field],b[field])
            self.assertEqual(a["results_applied_before_last_forecast"],1)
    def test_explicit_clock_required(self):
        for cls,fn,_ in MODELS:
            a,b=pair(cls,0,119)
            for rows in ([replace(a,forecast_utc=None),b],[replace(a,forecast_utc=None),replace(b,forecast_utc=None)]):
                with self.assertRaises(ValueError):fn(rows,warmup=1,require_explicit_forecast=True)
    def test_mixed_clock_rejected_even_legacy(self):
        for cls,fn,_ in MODELS:
            a,b=pair(cls,0,119)
            with self.assertRaises(ValueError):fn([replace(a,forecast_utc=None),b],warmup=1)
    def test_late_and_naive_forecast(self):
        for cls,fn,_ in MODELS:
            a,b=pair(cls,0,119)
            for invalid in (BASE+timedelta(minutes=171),datetime(2026,11,1,14)):
                with self.assertRaises(ValueError):fn([a,replace(b,forecast_utc=invalid)],warmup=1)
    def test_synthetic_mode_labeled(self):
        for cls,fn,_ in MODELS:
            a,b=pair(cls,0,119)
            r=fn([replace(a,forecast_utc=None),replace(b,forecast_utc=None)],warmup=1)
            self.assertEqual(r["forecast_cutoff_mode"],"SYNTHETIC_FIXED_10_MINUTE_LEAD")
            self.assertFalse(r["forecast_clock_authenticated"])
    def test_same_forecast_group_warmup(self):
        for cls,fn,_ in MODELS:
            rows=roster(cls)
            first=BASE-timedelta(hours=1)
            rows=[replace(r,forecast_utc=first if i<4 else BASE+timedelta(hours=5)) for i,r in enumerate(rows)]
            r=fn(rows,warmup=1,require_explicit_forecast=True)
            self.assertEqual(r["effective_warmup"],4)
            self.assertEqual(r["n_test"],1)
    def test_reject_inconsistent_same_kickoff(self):
        for cls,fn,_ in MODELS:
            rows=roster(cls)
            rows=[replace(r,forecast_utc=(r.kickoff_utc if cls is Match else r.kickoff)-timedelta(minutes=10+i)) for i,r in enumerate(rows)]
            with self.assertRaises(ValueError):fn(rows,warmup=1,require_explicit_forecast=True)
