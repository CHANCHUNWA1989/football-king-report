import json
import unittest
from pathlib import Path
from datetime import datetime,timezone
from ops.research_replay_attribution_v36 import attribute,summarize
from ops.research_attack_defence_replay_v35 import from_root

def row(n=1):
    return {"league":"epl","forecast_day":"2026-10-10","strict":False,"y":0,
            "original":[.6,.2,.2],"expanded":[.4,.3,.3],"market":[.7,.2,.1],"extra_league_prior":n}
class ReplayAttributionTests(unittest.TestCase):
    def test_paired_direction(self):
        r=attribute([row()]);self.assertGreater(r["all"]["log_loss_delta"],0)
        self.assertGreater(r["all"]["brier_delta"],0)
        self.assertEqual(r["all"]["worse_log_loss_cases"],1)
    def test_zero_support_invariance(self):
        with self.assertRaises(ValueError):attribute([row(0)])
        r=row(0);r["expanded"]=r["original"]
        self.assertEqual(attribute([r])["all"]["log_loss_delta"],0)
    def test_small_sample_no_interval(self):
        self.assertIsNone(summarize([row()])["interval"]["lower"])
        self.assertIsNone(summarize([])["log_loss_delta"])
    def test_cluster_interval_deterministic(self):
        rows=[dict(row(),forecast_day=f"2026-10-{i:02}") for i in range(1,11) for _ in range(3)]
        a=summarize(rows);self.assertEqual(a,summarize(rows))
        self.assertGreater(a["interval"]["lower"],0)
    def test_actual_archive(self):
        root=Path(__file__).resolve().parents[2];ledger=root/"evidence/settled.json";raw=ledger.read_bytes()
        r=from_root(root,as_of=datetime.now(timezone.utc).isoformat(),include_diagnostics=True)
        a=r["attribution"];s=r["scenarios"]["24"]["all"]
        self.assertEqual(a["all"]["n"],r["targets"])
        self.assertEqual(sum(x["n"] for x in a["by_league"].values()),r["targets"])
        self.assertEqual(sum(x["n"] for x in a["by_extra_league_support"].values()),r["targets"])
        self.assertAlmostEqual(a["all"]["log_loss_delta"],s["expanded_history"]["log_loss"]-s["original_history"]["log_loss"])
        self.assertEqual(ledger.read_bytes(),raw)
        print("V36_REPLAY_ATTRIBUTION_SUMMARY "+json.dumps(a,sort_keys=True,allow_nan=False))
