"""Reproduce observed provider spellings; all rows below are test fixtures."""
import copy
import unittest
from datetime import datetime, timedelta, timezone
from ops.secondary_sources import collect, fixture, LEAGUES
from ops.score_corroboration import audit, identity

class Empty:
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,size): return b'{"events":[]}'

class ScoreCorroborationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.doc = collect(now=self.now, keys={}, requester=lambda req, timeout: Empty())
        pairs = [
            ("Nottingham Forest","Chelsea","Nottingham Forest FC","Chelsea FC"),
            ("Southampton","Middlesbrough","Southampton FC","Middlesbrough FC"),
            ("Werder Bremen","Borussia Mönchengladbach","SV Werder Bremen","Borussia Mönchengladbach"),
            ("Levante","Racing de Santander","Levante UD","Real Racing Club de Santander"),
            ("Venezia","Bologna","Venezia FC","Bologna FC 1909"),
            ("Brest","Paris FC","Stade Brestois 29","Paris FC"),
        ]
        for provider, offset in (("thesportsdb",0),("football_data_org",2)):
            state = next(p for p in self.doc["providers"] if p["provider"] == provider)
            state.update(configured=True,status="PARTIAL",sampled_fixture_count=6,
                         counts_by_league=dict.fromkeys(LEAGUES,1))
            if provider == "thesportsdb":
                state["recent_final_score_observations"] = 6
            for i,(league,names) in enumerate(zip(LEAGUES,pairs)):
                row = fixture(league,names[offset],names[offset+1],
                              (self.now-timedelta(hours=4)).isoformat(),str(i),
                              score=[i%3,1],status="FINISHED")
                row["provider"]=provider
                self.doc["sampled_fixtures"].append(row)
        self.doc["collected_utc"]=self.now.isoformat()
    def test_all_six_exact_pairs(self):
        out=audit(self.doc,self.now)
        self.assertEqual(out["two_publisher_score_candidates"],6)
        self.assertEqual(out["authenticated_forward_samples"],0)
        self.assertEqual(out["production_recommendations"],"DISABLED")
    def test_disagreement(self):
        self.doc["sampled_fixtures"][-1]["score_ft"]=[9,9]
        out=audit(self.doc,self.now)
        self.assertEqual(out["two_publisher_score_candidates"],5)
        self.assertEqual(out["rejected"]["CONFLICTING_SCORE"],1)
    def test_wrong_kickoff(self):
        self.doc["sampled_fixtures"][-1]["kickoff_utc"]=(self.now-timedelta(hours=4,minutes=1)).isoformat()
        self.assertEqual(audit(self.doc,self.now)["two_publisher_score_candidates"],5)
    def test_premature_snapshot(self):
        for row in self.doc["sampled_fixtures"]:
            row["kickoff_utc"]=(self.now-timedelta(minutes=30)).isoformat()
        self.assertEqual(audit(self.doc,self.now)["two_publisher_score_candidates"],0)
    def test_no_fuzzy_or_cross_league_alias(self):
        self.assertNotEqual(identity("epl","Levante"),identity("epl","Levante UD"))
        self.assertNotEqual(identity("laliga","Real Racing Club de Santander"),identity("laliga","Racing Ferrol"))
    def test_invalid_totals_fail_closed(self):
        self.doc["providers"][0]["sampled_fixture_count"]+=1
        with self.assertRaises(ValueError):
            audit(self.doc,self.now)
    def test_stale_source(self):
        with self.assertRaisesRegex(ValueError,"STALE_OR_FUTURE_SOURCE"):
            audit(self.doc,self.now+timedelta(days=3))
