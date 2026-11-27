import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_snapshot_commitment import commitment
from test_live_snapshot_commitment import envelope, NOW
from vnext_integrated_replay import replay

class IntegratedReplayTests(unittest.TestCase):
    def test_normalized_research_only(self):
        e = envelope()
        out = replay(e, commitment(e), NOW)
        self.assertEqual(out["replay_status"], "RESEARCH_ONLY")
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["production_recommendations"], "DISABLED")
        self.assertAlmostEqual(sum(out["probabilities_1x2"].values()), 1)
        for m in out["diagnostic_distributions"]:
            self.assertAlmostEqual(sum(m["outcome_probabilities"].values()), 1)
        self.assertIsNone(out["actual_xg"])
        self.assertIsNone(out["model_edge"])
    def test_tamper_and_stale_clock(self):
        e = envelope()
        d = commitment(e)
        for now in (NOW+1, NOW+100):
            out = replay(e, d, now)
            self.assertEqual(out["status"], "HOLD")
            self.assertNotIn("probabilities_1x2", out)
        e["a"]["home"] = 1
        out = replay(e, d, NOW)
        self.assertEqual(out["status"], "HOLD")
        self.assertNotIn("probabilities_1x2", out)
    def test_origin_conflict_even_with_recomputed_hash(self):
        e = envelope()
        e["b"]["origin"] = e["a"]["origin"]
        out = replay(e, commitment(e), NOW)
        self.assertEqual(out["status"], "HOLD")
        self.assertFalse(out["source_independence_verified"])
        self.assertFalse(out["positive_ev_verified"])
