import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_deep_state_uncertainty import intervals,assess,METRICS,FAMILY

class DeepStateUncertaintyTests(unittest.TestCase):
    def test_sparse_blocks_not_zero_interval(self):
        r=intervals([(2,(-.1,)*len(METRICS))])
        self.assertEqual(r["n"],2)
        self.assertFalse(r["descriptive_coverage_eligible"])
        self.assertEqual(r["bootstrap_draws"],0)
        self.assertIsNone(r["metrics"]["-1.5"]["brier"]["adjusted_descriptive_interval"])
    def test_fixed_synthetic_blocks_direction_and_reproducibility(self):
        w=[(5,(-.5,)*len(METRICS)) for _ in range(12)]
        a=intervals(w)
        b=intervals(w)
        self.assertEqual(a,b)
        self.assertEqual(a["n"],60)
        self.assertEqual(FAMILY,24)
        for l,m in METRICS:
            v=a["metrics"][l][m]
            self.assertEqual(v["direction"],"LOWER_ERROR_INTERVAL")
            self.assertAlmostEqual(v["candidate_minus_baseline"],-.1)
            self.assertAlmostEqual(v["adjusted_descriptive_interval"][0],-.1)
            self.assertAlmostEqual(v["leave_one_week_out_range"][1],-.1)
    def test_bad_block_rejected(self):
        for w in ([(True,(0.,)*len(METRICS))],[(1,(float("nan"),)*len(METRICS))],[(1,(0.,))]):
            with self.assertRaises(ValueError):intervals(w)
    def test_replay_point_estimates_and_overlap(self):
        train=[("2020-01-01","A","B",2,0,4,1),("2020-01-02","C","D",0,2,1,2)]
        test=[("2021-01-01","A","B",2,0,3,0),("2021-01-08","C","D",0,2,1,4)]
        self.assertEqual(assess(train,test)["n"],2)
        with self.assertRaisesRegex(ValueError,"TEMPORAL_OVERLAP"):assess(train,train)
