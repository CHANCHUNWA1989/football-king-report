import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from ops.unified_market_grid import build,distribution
from ops.shadow_forecast import poisson_1x2
from ops.asian_handicap_research import probabilities
from ops.all_market_scenarios import total_scenario

class UnifiedGridTests(unittest.TestCase):
    def test_grid_matches_existing_quarter_settlement(self):
        for h,a in ((.1,.1),(1.7,1.1),(5.5,5.5)):
            d=distribution(h,a)
            self.assertAlmostEqual(sum(d["derived_1x2"]),1)
            self.assertEqual(len(d["asian_handicap"]),82)
            self.assertEqual(len(d["totals"]),42)
            for s in d["asian_handicap"]:
                old=probabilities(h,a,s["side"],s["hypothetical_line"])["outcome_probabilities"]
                for k,v in s["probabilities"].items():
                    self.assertAlmostEqual(v,old[k],places=6)
            for s in d["totals"]:
                old=total_scenario(h,a,side=s["side"],line=s["hypothetical_line"])["settlement_probabilities"]
                for k,v in s["probabilities"].items():
                    self.assertAlmostEqual(v,old[k],places=6)
    def test_opposite_sides_are_complements(self):
        d=distribution(2.2,1.4)
        ah={(s["side"],s["hypothetical_line"]):s["probabilities"] for s in d["asian_handicap"]}
        for u in (-1.25,0,.75,5):
            x,y=ah["HOME",u],ah["AWAY",-u]
            for k,l in (("FULL_WIN","FULL_LOSS"),("HALF_WIN","HALF_LOSS"),("PUSH","PUSH")):
                self.assertAlmostEqual(x[k],y[l])
    def inputs(self):
        n=datetime(2026,11,26,10,tzinfo=timezone.utc)
        p=poisson_1x2(1.7,1.1)
        row=dict(event_id="1",league="epl",home="A",away="B",
                 model="poisson-shrinkage-unvalidated-v4.1",
                 production_recommendations="DISABLED",calibrated=False,verified_market_odds=False,
                 kickoff_utc=(n+timedelta(hours=3)).isoformat(),prediction_utc=n.isoformat(),
                 expected_home_goals=1.7,expected_away_goals=1.1,p_home=p[0],p_draw=p[1],p_away=p[2])
        return n,row,dict(status="SHADOW_ONLY",as_of_utc=n.isoformat(),
                         production_recommendations="DISABLED",model_calibrated=False,predictions=[row])
    def test_all_valid_rows_not_eight_match_limit(self):
        n,r,doc=self.inputs()
        doc["predictions"]=[dict(r,event_id=str(i)) for i in range(12)]
        out=build(doc,None,now=n)
        self.assertEqual(out["qualified_research_rows"],12)
        self.assertEqual(out["recommendations"],[])
        self.assertFalse(out["positive_ev_verified"])
    def test_mismatch_and_duplicate_and_late_rejected(self):
        n,r,doc=self.inputs()
        for bad in ([r,r],[dict(r,p_home=.5,p_draw=.25,p_away=.25)],
                    [dict(r,kickoff_utc=n.isoformat())],[dict(r,score_ft=[1,0])]):
            doc["predictions"]=bad
            self.assertEqual(build(doc,None,now=n)["qualified_research_rows"],0)
        doc["predictions"]=[r]
        self.assertEqual(build(doc,None,now=n+timedelta(hours=11))["status"],"HOLD")

    def test_output_bound_is_counted_without_promotion(self):
        n,r,doc=self.inputs()
        doc["predictions"]=[dict(r,event_id=str(i)) for i in range(3)]
        with patch("ops.unified_market_grid.MAX_OUTPUT_ROWS",1):
            out=build(doc,None,now=n)
        self.assertEqual(out["qualified_research_rows"],1)
        self.assertEqual(out["output_bound_omissions"],2)
        self.assertEqual(out["source_row_counts"]["core"],3)
        self.assertFalse(out["coverage_complete"])
        self.assertEqual(out["recommendations"],[])

    def test_byte_bound_and_blank_identity(self):
        n,r,doc=self.inputs()
        doc["predictions"]=[r,dict(r,event_id=" ")]
        with patch("ops.unified_market_grid.MAX_OUTPUT_BYTES",1):
            out=build(doc,None,now=n)
        self.assertEqual(out["output_bound_omissions"],1)
        self.assertEqual(out["exclusions"]["AMBIGUOUS_IDENTITY"],1)
        self.assertEqual(out["qualified_research_rows"],0)

if __name__=="__main__":
    unittest.main()
