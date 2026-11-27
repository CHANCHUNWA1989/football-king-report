import unittest
import json
from datetime import datetime,timezone
from pathlib import Path
from ops.research_market_fusion_v37 import candidate,evaluate
from ops.research_attack_defence_replay_v35 import from_root
P=[.6,.2,.2];M=[.4,.3,.3]
class MarketFusionTests(unittest.TestCase):
    def test_zero_support_is_market(self):
        r=candidate(P,M,support=(10,5,0,2),market_age_seconds=0)
        self.assertEqual(r["weight"],0)
        self.assertEqual(r["p"],M)
    def test_cap_and_monotonic_support(self):
        low=candidate(P,M,support=(10,10,2,2),market_age_seconds=3600)
        high=candidate(P,M,support=(40,20,5,5),market_age_seconds=3600)
        self.assertAlmostEqual(low["weight"],.04)
        self.assertEqual(high["weight"],.1)
        self.assertAlmostEqual(sum(high["p"]),1)
    def test_stale_abstain(self):
        self.assertIsNone(candidate(P,M,support=(40,20,5,5),market_age_seconds=3601)["p"])
    def test_invalid_metadata(self):
        for s,t in (((10,11,1,1),0),((10,5,1,1),-1),((10,5,True,1),0)):
            with self.assertRaises(ValueError):candidate(P,M,support=s,market_age_seconds=t)
    def test_paired_cohort(self):
        rows=[dict(expanded=P,market=M,expanded_support=(40,20,5,5),market_age_seconds=t,y=0) for t in (3600,3601)]
        r=evaluate(rows)
        self.assertEqual(r["paired_count"],1)
        self.assertEqual({m["n"] for m in r["models"].values()},{1})
        self.assertFalse(r["model_promotion_allowed"])
    def test_paired_diagnostics_identical_roster(self):
        rows=[dict(expanded=P,market=M,expanded_support=(40,20,5,5),
                   market_age_seconds=0,forecast_day=f"2026-10-{i:02}",y=0)
              for i in range(1,11) for _ in range(3)]
        rows.append(dict(rows[0],market_age_seconds=3601))
        report=evaluate(rows,paired_diagnostics=True)
        self.assertEqual(report["paired_count"],30)
        for name,v in report["paired_vs_market"].items():
            self.assertEqual(v["n"],30)
            self.assertAlmostEqual(v["log_loss_delta"],report["models"][name]["log_loss"]-report["models"]["market"]["log_loss"])
            self.assertLess(v["interval"]["upper"],0)
        self.assertFalse(report["paired_diagnostic_policy"]["independent_inference"])
    def test_zero_weight_and_small_sample(self):
        r=dict(expanded=P,market=M,expanded_support=(10,5,0,2),
               market_age_seconds=0,forecast_day="2026-10-01",y=0)
        report=evaluate([r],paired_diagnostics=True)
        self.assertEqual(report["paired_vs_market"]["adaptive_capped"]["log_loss_delta"],0)
        self.assertIsNone(report["paired_vs_market"]["adaptive_capped"]["interval"]["lower"])
    def test_invalid_forecast_day(self):
        r=dict(expanded=P,market=M,expanded_support=(10,5,0,2),
               market_age_seconds=0,forecast_day="invalid",y=0)
        with self.assertRaises(ValueError):
            evaluate([r],paired_diagnostics=True)
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2]
        ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat(),include_fusion=True)["market_fusion"]
        self.assertEqual(sum(r["states"].values()),r["target_count"])
        self.assertEqual({m["n"] for m in r["models"].values()},{r["paired_count"]})
        for name,v in r["paired_vs_market"].items():
            self.assertEqual(v["n"],r["paired_count"])
            if v["n"]:
                self.assertAlmostEqual(v["log_loss_delta"],r["models"][name]["log_loss"]-r["models"]["market"]["log_loss"])
        self.assertEqual(ledger.read_bytes(),raw)
        print("V37_MARKET_FUSION_SUMMARY "+json.dumps(r,sort_keys=True,allow_nan=False))
