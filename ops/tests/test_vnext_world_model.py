"""Synthetic path simulation and existing evidence-cut contract."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_live_evidence_cut import sample,NOW
from vnext_live_evidence_cut import cut_digest
from inplay_state_challenger_vnext import remaining_matrix
from score_distribution_vnext import one_x_two
from vnext_world_model import simulate,hazards,research_cut,wilson

class WorldModelTests(unittest.TestCase):
    def test_constant_hazard_matches_exact_poisson_within_mc_tolerance(self):
        g,d=simulate(1.6,1.2,45,[0,1],[0,0],paths=16384,
                     score_coef=0.,card_coef=0.,card_rate=0.)
        p=one_x_two(g);q=one_x_two(remaining_matrix(.8,.6,0,1))
        for k in p:self.assertLess(abs(p[k]-q[k]),.025)
        self.assertEqual(d["additional_red_card_path_probability"],0)
        self.assertAlmostEqual(sum(d["first_event"].values()),1)
    def test_reproducible_and_card_response(self):
        a=simulate(1.6,1.2,50,[0,0],[0,0],paths=2048)
        self.assertEqual(a,simulate(1.6,1.2,50,[0,0],[0,0],paths=2048))
        normal=hazards(1.6,1.2,0,0,0,0)
        card=hazards(1.6,1.2,0,0,1,0)
        self.assertLess(card[0],normal[0]);self.assertGreater(card[1],normal[1])
        self.assertEqual(hazards(1.6,1.2,0,0,3,0)[2],0)
        self.assertGreater(hazards(1.6,1.2,0,1,0,0)[0],normal[0])
    def test_bound_cut_shared_grid_and_price_independence(self):
        e,s=sample()
        a=research_cut(e,s,cut_digest(e,s),NOW)
        self.assertEqual(a["world_model_status"],"STRUCTURAL_RESEARCH_ONLY")
        self.assertAlmostEqual(sum(a["probabilities_1x2"].values()),1)
        self.assertAlmostEqual(sum(a["market_distribution"]["outcome_probabilities"].values()),1)
        self.assertEqual(a["probabilities_1x2"],one_x_two(a["score_matrix"]))
        s["quote"]["decimal_price"]=2.1
        b=research_cut(e,s,cut_digest(e,s),NOW)
        self.assertEqual(a["score_matrix"],b["score_matrix"])
        self.assertFalse(b["model_uncertainty_calibrated"])
        self.assertEqual(b["production_recommendations"],"DISABLED")
        self.assertEqual(b["verified_forward_sample_credit"],0)
        self.assertIsNone(b["actual_xg"])
        self.assertNotIn("world_model_status",research_cut(e,s,"0"*64,NOW))
    def test_invalid_state_and_intervals(self):
        with self.assertRaises(ValueError):simulate(1.6,1.2,90,[0,0],[0,0])
        with self.assertRaises(ValueError):simulate(1.6,1.2,50,[0,0],[4,0])
        with self.assertRaises(ValueError):simulate(1.6,1.2,50,[0,0],[0,0],paths=999999)
        for p in (0.,.5,1.):
            lo,hi=wilson(p,8192)
            self.assertLessEqual(lo,p+1e-12);self.assertGreaterEqual(hi,p-1e-12)
