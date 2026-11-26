"""Cross-module synthetic integration; not real forecast evidence."""
import copy
import json
import unittest
from datetime import datetime,timedelta,timezone
from ops.global_full_slate import build as slate
from ops.worldwide_shadow import generate
from ops.unified_market_grid import build as grid
from ops.shadow_forecast import poisson_1x2
from ops.operations_review import build as review
from ops.live_state_sensitivity import evaluate

NOW=datetime(2026,11,26,10,tzinfo=timezone.utc)
KO=(NOW+timedelta(hours=2)).isoformat()
def doc(**kwargs):
    return {"production_recommendations":"DISABLED",**kwargs}

class SixPhaseIntegrationTests(unittest.TestCase):
    def test_single_provider_schedule_is_visible_not_model_qualified(self):
        row={"provider":"thesportsdb","provider_event_id":"123","home":"A","away":"B",
             "kickoff_utc":KO,"captured_utc":NOW.isoformat(),"status":"SCHEDULED","score_ft":None}
        world=doc(schema="football-king-worldwide-candidate-input-v1",
                   collected_utc=NOW.isoformat(),
                   leagues=[{"id":"small_cup","history":[],"fixture_observations":[row]}])
        original=copy.deepcopy(world)
        prediction=generate(world,now=NOW)
        ledger=slate({"fixtures":{"matches":[]}},world,None,prediction,
                     now=NOW,start=NOW-timedelta(hours=10),end=NOW+timedelta(days=1))
        market=grid(None,prediction,now=NOW)
        report=review({"global_full_slate":ledger,"unified_market_grid":market,
                       "worldwide_shadow":prediction},now=NOW)
        self.assertEqual(world,original)
        self.assertEqual(ledger["counts"]["input_rows"],1)
        self.assertEqual(len(ledger["rows"]),1)
        self.assertEqual(prediction["predictions_count"],0)
        self.assertEqual(market["qualified_research_rows"],0)
        self.assertEqual(report["status"],"HOLD")
        self.assertFalse(report["global_coverage_complete"])
        self.assertEqual(report["authenticated_forward_samples"],0)

    def test_exact_core_reference_and_grid_without_promotion(self):
        p=poisson_1x2(1.7,1.1)
        row=doc(event_id="123",league="epl",home="A",away="B",
                 kickoff_utc=KO,prediction_utc=NOW.isoformat(),
                 model="poisson-shrinkage-unvalidated-v4.1",calibrated=False,
                 verified_market_odds=False,expected_home_goals=1.7,expected_away_goals=1.1,
                 p_home=p[0],p_draw=p[1],p_away=p[2])
        shadow=doc(status="SHADOW_ONLY",model_calibrated=False,
                   as_of_utc=NOW.isoformat(),predictions=[row])
        original=copy.deepcopy(shadow)
        fixture={**row,"status":"SCHEDULED"}
        ledger=slate({"fixtures":{"matches":[fixture,fixture]}},None,shadow,None,
                     now=NOW,start=NOW-timedelta(hours=10),end=NOW+timedelta(days=1))
        market=grid(shadow,None,now=NOW)
        report=review({"global_full_slate":ledger,"unified_market_grid":market},now=NOW)
        self.assertEqual(shadow,original)
        self.assertEqual(ledger["counts"]["duplicate_observations"],1)
        self.assertEqual(ledger["counts"]["exact_core_model_reference_observations"],1)
        self.assertEqual(market["qualified_research_rows"],1)
        self.assertEqual(len(market["rows"][0]["derived_grid"]["asian_handicap"]),82)
        self.assertEqual(len(market["rows"][0]["derived_grid"]["totals"]),42)
        self.assertEqual(ledger["qualified_recommendations"],0)
        self.assertEqual(market["recommendations"],[])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertEqual(evaluate(None,[],as_of_utc=NOW.isoformat(),
                                  assumed_full_match_rates=(1.7,1.1))["status"],"HOLD")

    def test_json_roundtrip_unsafe_and_unknown(self):
        ledger=slate(None,None,None,None,now=NOW,start=NOW,end=NOW+timedelta(days=1))
        market=grid(None,None,now=NOW)
        report=review(json.loads(json.dumps({"global_full_slate":ledger,
                 "unified_market_grid":market,"quality":{"production_recommendations":"ENABLED",
                 "public_matches":100}})),now=NOW)
        self.assertIsNone(report["counts"]["public_window_observations"])
        self.assertIn("UNSAFE_QUALITY",[a["code"] for a in report["alerts"]])
        self.assertEqual(report["authenticated_forward_samples"],0)

if __name__=="__main__":
    unittest.main()
