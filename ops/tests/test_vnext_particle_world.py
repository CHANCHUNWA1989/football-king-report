"""Synthetic SMC tests, no authenticated real events."""
import math
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_vnext_native_series_replay import case,KO
from vnext_particle_world import transition_loglik,particle_filter,research_series,PARTICLES
from vnext_world_model import hazards
from score_distribution_vnext import one_x_two

def state(minute,h=0,a=0,rh=0,ra=0):
    return {"minute":minute,"score":[h,a],"red_cards":[rh,ra]}

class ParticleWorldTests(unittest.TestCase):
    def test_zero_and_one_event_likelihood(self):
        a,b=state(10),state(20)
        self.assertAlmostEqual(transition_loglik(1.5,1.2,a,b),-10*sum(hazards(1.5,1.2,0,0,0,0)))
        self.assertTrue(math.isfinite(transition_loglik(1.5,1.2,a,state(20,h=1))))
        self.assertTrue(math.isfinite(transition_loglik(1.5,1.2,a,state(20,rh=1))))
        for bad in (state(20,h=2),state(10,h=1),state(9)):
            with self.assertRaises(ValueError):transition_loglik(1.5,1.2,a,bad)
    def test_sequential_updates_and_reproducibility(self):
        no=[state(10),state(40)]
        goal=[state(10),state(40,h=1)]
        a=particle_filter(1.5,1.2,no)
        b=particle_filter(1.5,1.2,goal)
        self.assertEqual(a,particle_filter(1.5,1.2,no))
        self.assertAlmostEqual(sum(a[1]),1)
        self.assertGreater(b[2][0]["posterior_rate_means"][0],a[2][0]["posterior_rate_means"][0])
        self.assertLessEqual(a[2][0]["ess_before_resample"],PARTICLES+1e-8)
    def test_series_grid_and_tamper(self):
        raw,digest,cuts=case()
        args=dict(fixture_id="openligadb:123",home_native_id="10",away_native_id="20",kickoff_utc=KO,cuts=cuts)
        a=research_series(raw,digest,**args)
        self.assertEqual(a["particle_status"],"STRUCTURAL_RESEARCH_ONLY")
        self.assertEqual(a["conditioned_intervals"],1)
        self.assertEqual(a["probabilities_1x2"],one_x_two(a["score_matrix"]))
        self.assertAlmostEqual(sum(a["market_distribution"]["outcome_probabilities"].values()),1)
        self.assertFalse(a["learned_v11_state_connected"])
        self.assertEqual(a["verified_forward_sample_credit"],0)
        self.assertEqual(a["production_recommendations"],"DISABLED")
        cuts[1]["snapshot"]["quote"]["decimal_price"]=2.1
        self.assertNotIn("particle_status",research_series(raw,digest,**args))
