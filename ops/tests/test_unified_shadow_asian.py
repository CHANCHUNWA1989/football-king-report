"""Cross-check unified Asian scenarios against exact settlement and invariants."""
import math
import unittest

from ops.asian_handicap_research import grade
from ops.unified_shadow_integration import (
    GRADES, HANDICAP_Q, TOTAL_Q, asian_scenarios, distribution_from_matrix,
    marginal_scores, score_matrix, settlement_grade,
)


class UnifiedAsianTests(unittest.TestCase):
    def test_handicap_matches_existing_settler(self):
        for h in range(8):
            for a in range(8):
                for q in HANDICAP_Q:
                    for side in ("HOME", "AWAY"):
                        self.assertEqual(settlement_grade(h-a,"HANDICAP",side,q),
                                         grade(h,a,side,q/4))

    def test_total_quarters(self):
        cases = [(2,"OVER",9,"HALF_LOSS"),(2,"UNDER",9,"HALF_WIN"),
                 (3,"OVER",11,"HALF_WIN"),(3,"UNDER",11,"HALF_LOSS"),
                 (3,"OVER",12,"PUSH"),(3,"UNDER",12,"PUSH"),
                 (2,"OVER",10,"FULL_LOSS"),(3,"OVER",10,"FULL_WIN")]
        for goals,side,q,want in cases:
            self.assertEqual(settlement_grade(goals,"TOTAL",side,q),want)

    def test_all_scenarios_mass_and_opposites(self):
        for h,a in ((.1,.1),(1.2,1.2),(2.1,.8),(5.5,5.5)):
            score=score_matrix(h,a)
            margin,total=marginal_scores(score)
            rows=asian_scenarios(margin,total)
            self.assertEqual(len(rows),84)
            for i in range(0,len(rows),2):
                first,second=rows[i:i+2]
                p,q=first["outcome_probabilities"],second["outcome_probabilities"]
                self.assertAlmostEqual(sum(p.values()),1,places=10)
                self.assertAlmostEqual(sum(q.values()),1,places=10)
                for k,opposite in zip(GRADES,reversed(GRADES)):
                    self.assertAlmostEqual(p[k],q[opposite],places=10)
                self.assertTrue(first["hypothetical_line_not_market_quote"])
            base=distribution_from_matrix(score,margin,total)
            dnb=next(r["outcome_probabilities"] for r in rows if r["market"]=="HANDICAP" and r["side"]=="HOME" and r["line_quarter_units"]==0)
            self.assertAlmostEqual(dnb["FULL_WIN"],base["p_home"])
            self.assertAlmostEqual(dnb["PUSH"],base["p_draw"])
            self.assertAlmostEqual(dnb["FULL_LOSS"],base["p_away"])
            over=next(r["outcome_probabilities"] for r in rows if r["market"]=="TOTAL" and r["side"]=="OVER" and r["line_quarter_units"]==10)
            self.assertAlmostEqual(over["FULL_WIN"],base["p_over_2_5"])
            self.assertAlmostEqual(over["FULL_LOSS"],base["p_under_2_5"])

    def test_invalid_inputs(self):
        for args in [(1,"TOTAL","OVER",2),(1,"TOTAL","HOME",10),
                     (-1,"TOTAL","OVER",10),(1,"HANDICAP","HOME",True),
                     (1,"HANDICAP","AWAY",13),(1,"HANDICAP","AWAY",.25)]:
            with self.subTest(args=args),self.assertRaises(ValueError):
                settlement_grade(*args)

    def test_low_and_high_rates(self):
        for h,a in ((.1,5.5),(5.5,.1),(5.5,5.5)):
            matrix=score_matrix(h,a)
            self.assertAlmostEqual(math.fsum(map(math.fsum,matrix)),1,places=12)


if __name__=="__main__":
    unittest.main()
