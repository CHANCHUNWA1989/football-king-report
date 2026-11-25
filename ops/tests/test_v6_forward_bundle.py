import copy
import unittest
from datetime import datetime,timezone
from ops.v6_forward_bundle import pack,SCOPES,WEIGHTS,NAMES
from ops.v5_integration_acceptance import grid,summary
NOW=datetime(2026,11,25,14,5,tzinfo=timezone.utc)
def inputs():
    d={}
    for k,l in SCOPES.items():
        d[k]={"league":l,"provider_league_shortcut":k,"provider":"OpenLigaDB","production_recommendations":"DISABLED",
            "verified_forward_sample_credit":0,"automatic_promotion":False,"weights":WEIGHTS,"generated_utc":"2026-11-25T14:04:00Z",
            "status":"HOLD","predictions":[],"predictions_count":0}
    r=d["bl1"];r.update(status="SHADOW_ONLY",predictions_count=1,season=2026,
        source_receipts=[{"source":f"https://api.openligadb.de/getmatchdata/bl1/{y}","captured_utc":"2026-11-25T14:03:00Z","sha256":"a"*64} for y in (2025,2026)])
    p=summary(grid(0,0,1.5,1.))["1x2"]
    r["predictions"]=[{"provider_event_id":"1","home_native_id":"2","away_native_id":"3","home":"H","away":"A",
        "production_recommendations":"DISABLED","prediction_utc":"2026-11-25T14:04:00Z","kickoff_utc":"2026-11-26T14:00:00Z",
        "p_1x2":p,"model_probabilities":{k:p for k in NAMES},"joint_goal_rates":[1.5,1.]}]
    return d
class BundleTests(unittest.TestCase):
    def test_valid(self):
        r=pack(inputs(),NOW)
        self.assertEqual(r["predictions_count"],1)
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(len(r["predictions"][0]["joint_only_fixed_line_scenarios"]),4)
    def test_inconsistent_weights_or_probabilities(self):
        for field,value in (("p_1x2",[1,0,0]),("joint_goal_rates",[3.,1.])):
            d=inputs();d["bl1"]["predictions"][0][field]=value
            with self.assertRaises(ValueError):pack(d,NOW)
    def test_result_or_expired(self):
        for field,value in (("score_ft",[1,0]),("kickoff_utc","2026-11-25T14:10:00Z")):
            d=inputs();d["bl1"]["predictions"][0][field]=value
            with self.assertRaises(ValueError):pack(d,NOW)
    def test_missing_scope_and_release_flag(self):
        d=inputs();del d["bl2"]
        with self.assertRaises(ValueError):pack(d,NOW)
        d=inputs();d["bl2"]["production_recommendations"]="ENABLED"
        with self.assertRaises(ValueError):pack(d,NOW)
