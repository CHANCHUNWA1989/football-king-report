"""Same-kickoff and timezone invariance regression; synthetic inputs only."""
import unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from ops.research_walkforward_v1 import Match,walk_forward
from ops.research_team_ratings_v1 import Fixture,walk_forward_teams
from ops.research_result_clock import ResultClock,validate_result_clock

BASE=datetime(2026,11,1,12,tzinfo=timezone.utc)
def roster(cls):
    result=[]
    for fid,k,h,a,hg,ag in (("a",0,"H1","A1",4,0),("b",0,"H2","A2",0,3),
                              ("c",3,"H1","A2",1,1),("d",3,"H2","A1",2,0),
                              ("e",6,"H1","A1",1,0)):
        ko=BASE+timedelta(hours=k);available=ko+timedelta(hours=2)
        if cls is Match:result.append(Match(ko,hg,ag,True,available,fid))
        else:result.append(Fixture(ko,h,a,hg,ag,True,available,fid))
    return result

class SameKickoffTests(unittest.TestCase):
    def test_same_kickoff_permutation(self):
        for cls,fn in ((Match,walk_forward),(Fixture,walk_forward_teams)):
            a,b,c,d,e=roster(cls)
            x=fn([a,b,c,d,e],warmup=1)
            y=fn([b,a,d,c,e],warmup=1)
            self.assertEqual(x,y)
            self.assertEqual(x["effective_warmup"],2)
            self.assertEqual(x["n_test"],3)
            self.assertEqual(x["kickoff_groups"],3)
    def test_duplicate_fixed_id(self):
        for cls,fn in ((Match,walk_forward),(Fixture,walk_forward_teams)):
            rows=roster(cls);rows[-1]=replace(rows[-1],fixture_id="a")
            with self.assertRaises(ValueError):fn(rows,warmup=1)
    def test_missing_simultaneous_id(self):
        for cls,fn in ((Match,walk_forward),(Fixture,walk_forward_teams)):
            rows=roster(cls);rows[0]=replace(rows[0],fixture_id=None)
            with self.assertRaises(ValueError):fn(rows,warmup=1)
    def test_simultaneous_team_collision(self):
        rows=roster(Fixture);rows[1]=replace(rows[1],home=rows[0].home)
        with self.assertRaises(ValueError):walk_forward_teams(rows,warmup=1)
    def test_warmup_must_leave_whole_group(self):
        for cls,fn in ((Match,walk_forward),(Fixture,walk_forward_teams)):
            with self.assertRaises(ValueError):fn(roster(cls)[:2],warmup=1)
    def test_offsets_same_kickoff(self):
        rows=roster(Match);rows[1]=replace(rows[1],kickoff_utc=BASE.astimezone(timezone(timedelta(hours=8))))
        self.assertEqual(walk_forward(rows,warmup=1),walk_forward(roster(Match),warmup=1))
    def test_dst_elapsed_clock(self):
        z=ZoneInfo("America/New_York")
        start=datetime(2026,11,1,1,15,tzinfo=z,fold=0)
        finish=datetime(2026,11,1,1,45,tzinfo=z,fold=1)
        validate_result_clock(start,finish) # 90 elapsed minutes, not 30 wall-clock minutes
        clock=ResultClock();seen=[]
        clock.schedule(finish,"result")
        clock.drain_before(datetime(2026,11,1,1,50,tzinfo=z,fold=0),seen.append)
        self.assertEqual(seen,[])
        clock.drain_before(datetime(2026,11,1,1,50,tzinfo=z,fold=1),seen.append)
        self.assertEqual(seen,["result"])
