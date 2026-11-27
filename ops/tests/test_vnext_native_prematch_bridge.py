"""Synthetic native archive bridge tests. No source calls or certification."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_native_prematch_bridge import build_prematch
from inplay_state_challenger_vnext import predict
from test_inplay_state_challenger_vnext import sample, KO

def archive():
    return dict(schema="v5-native-forward-shadow-v1",
                provider="OpenLigaDB", league="bundesliga", provider_league_shortcut="bl1",
                model_id="v5-seven-model-native-bundesliga-shadow-v1",
                status="SHADOW_ONLY", production_recommendations="DISABLED",
                verified_forward_sample_credit=0, source_independent=False,
                result_authentication=False, external_capture_witness_verified=False,
                feature_availability_independently_verified=False, market_odds_available=False,
                automatic_promotion=False, generated_utc="2026-11-03T19:45:01Z",
                source_receipts=[dict(sha256="a"*64,captured_utc="2026-11-03T19:39:00Z"),
                                 dict(sha256="b"*64,captured_utc="2026-11-03T19:40:00Z")],
                predictions_count=1, predictions=[dict(provider_event_id="123",
                    home_native_id="10",away_native_id="20",kickoff_utc=KO,
                    prediction_utc="2026-11-03T19:45:00Z",joint_goal_rates=[1.65,1.4],
                    joint_rates_are_not_ensemble_goal_distribution=True,
                    production_recommendations="DISABLED",p_1x2=[.3,.3,.4])])

def bridge(doc, **overrides):
    raw=json.dumps(doc).encode()
    args=dict(fixture_id="openligadb:123",home_native_id="10",away_native_id="20",kickoff_utc=KO)
    args.update(overrides)
    return build_prematch(raw,hashlib.sha256(raw).hexdigest(),**args)

class BridgeTests(unittest.TestCase):
    def test_explicit_rates_feed_existing_dynamic_model(self):
        doc=archive()
        pre=bridge(doc)
        self.assertEqual((pre["expected_home_goals"],pre["expected_away_goals"]),(1.65,1.4))
        self.assertIn("joint-poisson-only",pre["model_id"])
        s=sample()
        s["fixture_id"]=s["event_consensus"]["fixture_id"]=pre["fixture_id"]
        s["prematch"]=pre
        out=predict(s)
        self.assertAlmostEqual(sum(out["fulltime_probabilities"].values()),1)
        self.assertFalse(out["positive_ev_verified"])
        self.assertFalse(out["model_scoring_eligible"])
        self.assertEqual(out["production_recommendations"],"DISABLED")
        doc["predictions"][0]["p_1x2"]=[.99,.005,.005]
        altered=bridge(doc)
        self.assertEqual(altered["expected_home_goals"],pre["expected_home_goals"])
        self.assertEqual(altered["expected_away_goals"],pre["expected_away_goals"])
    def test_identity_and_tamper(self):
        for args in (dict(fixture_id="other:123"),dict(fixture_id="openligadb:124"),
                     dict(home_native_id="20",away_native_id="10"),
                     dict(kickoff_utc="2026-11-03T20:01:00Z")):
            with self.subTest(args=args),self.assertRaises(ValueError):
                bridge(archive(),**args)
        raw=json.dumps(archive()).encode()
        with self.assertRaises(ValueError):
            build_prematch(raw,"f"*64,fixture_id="openligadb:123",
                home_native_id="10",away_native_id="20",kickoff_utc=KO)
    def test_missing_rates_invalid_rates_and_leakage(self):
        for key,val in (("joint_goal_rates",None),("joint_goal_rates",[True,1.4]),
                        ("joint_goal_rates",[8,1.4]),
                        ("joint_rates_are_not_ensemble_goal_distribution",False),
                        ("prediction_utc","2026-11-03T19:59:00Z")):
            doc=archive();doc["predictions"][0][key]=val
            with self.subTest(key=key,val=val),self.assertRaises(ValueError):
                bridge(doc)
        doc=archive();doc["source_receipts"][1]["captured_utc"]="2026-11-03T19:46:00Z"
        with self.assertRaises(ValueError):bridge(doc)
    def test_duplicate_fixture_and_non_shadow_rejected(self):
        doc=archive();doc["predictions"]*=2;doc["predictions_count"]=2
        with self.assertRaises(ValueError):bridge(doc)
        doc=archive();doc["source_independent"]=True
        with self.assertRaises(ValueError):bridge(doc)
        doc=archive();doc["schema"]="v8-8-ucl-calibration-research-v1"
        with self.assertRaises(ValueError):bridge(doc)
