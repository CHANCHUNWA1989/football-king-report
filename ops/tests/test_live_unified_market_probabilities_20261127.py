import unittest
from math import fsum
from ops.live_unified_market_probabilities_20261127 import unified_markets,transition_markets,OUTCOMES
from ops.live_snapshot_market_audit_20261126 import profit
from ops.live_score_challenger_20261127 import score_grid

LINES=[x/4 for x in range(-12,13)]
TOTALS=[x/4 for x in range(25)]
NEUTRAL=dict(own_red_log=0,opponent_red_log=0,trailing_log=0,leading_log=0)

class UnifiedMarketsTests(unittest.TestCase):
    def assert_pair(self,left,right):
        self.assertAlmostEqual(fsum(left.values()),1,places=12)
        self.assertAlmostEqual(fsum(right.values()),1,places=12)
        for k,j in zip(OUTCOMES,reversed(OUTCOMES)):
            self.assertAlmostEqual(left[k],right[j],places=12)
    def test_deterministic_grid(self):
        # 36 score states x (25 handicap pairs + 25 total pairs).
        lookup={1:"full_win",.5:"half_win",0:"push",-.5:"half_loss",-1:"full_loss"}
        for h in range(6):
            for a in range(6):
                r=unified_markets({(h,a):1},LINES,TOTALS,scope="FULL_MATCH")
                for x in r["handicaps"]:
                    self.assert_pair(x["home"],x["away"])
                    self.assertEqual(x["home"][lookup[profit(h-a,x["home_line"],2)]],1)
                for x in r["totals"]:
                    self.assert_pair(x["over"],x["under"])
                    self.assertEqual(x["over"][lookup[profit(h+a,-x["line"],2)]],1)
    def test_mixed_grid_consistency(self):
        g={(0,0):.2,(1,0):.3,(0,1):.1,(2,1):.4}
        r=unified_markets(g,[-.75,0,.75],[.5,1,1.5,2,2.5],scope="FULL_MATCH")
        self.assertEqual(r["one_x_two"],[.7,.2,.1])
        dnb=r["handicaps"][1]["home"]
        self.assertAlmostEqual(dnb["full_win"],.7)
        self.assertAlmostEqual(dnb["push"],.2)
        self.assertAlmostEqual(dnb["full_loss"],.1)
        self.assertAlmostEqual(r["handicaps"][0]["home"]["half_win"],.7)
        self.assertAlmostEqual(r["both_teams_score"],.4)
        self.assertAlmostEqual(r["expected_final_goals"],1.6)
    def test_transition_integration(self):
        for score in [(0,0),(1,0),(0,2)]:
            for rates in [(1,1),(2,.7),(.7,2)]:
                r=transition_markets(score,(0,0),2700,rates,handicap_lines=LINES,
                                     total_lines=TOTALS,scope="FULL_MATCH",**NEUTRAL)
                ref=unified_markets(score_grid(score,rates[0]/2,rates[1]/2),
                                    LINES,TOTALS,scope="FULL_MATCH")
                for p,q in zip(r["one_x_two"],ref["one_x_two"]):
                    self.assertAlmostEqual(p,q,places=11)
                for group,left,right in [("handicaps","home","away"),("totals","over","under")]:
                    for x,y in zip(r[group],ref[group]):
                        self.assert_pair(x[left],x[right])
                        for side in (left,right):
                            for k in OUTCOMES:
                                self.assertAlmostEqual(x[side][k],y[side][k],places=11)
                self.assertFalse(r["qualified"])
                self.assertFalse(r["positive_ev_verified"])
                self.assertEqual(r["deployment"],"HOLD")
    def test_reject_invalid(self):
        for g in ({},{(0,0):.9},{(0,0):True},{(True,0):1},{(0,0):float("nan")},
                  {(0,0):1.1,(1,0):-.1}):
            with self.subTest(grid=g),self.assertRaises(ValueError):
                unified_markets(g,[0],[2.5],scope="FULL_MATCH")
        for lines,totals,scope in [([0,0],[2.5],"FULL_MATCH"),([.1],[2.5],"FULL_MATCH"),
                                    ([0],[-.5],"FULL_MATCH"),([0],[2.5],"REMAINING")]:
            with self.subTest(lines=lines,totals=totals,scope=scope),self.assertRaises(ValueError):
                unified_markets({(0,0):1},lines,totals,scope=scope)

if __name__=="__main__": unittest.main()
