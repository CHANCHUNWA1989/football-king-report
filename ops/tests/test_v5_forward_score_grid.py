import unittest
from datetime import datetime,timezone,timedelta
from ops.v5_forward_score_grid import forward
from ops.v5_integration_acceptance import grid,summary
NOW=datetime(2026,11,25,14,tzinfo=timezone.utc)
def source(lead=3600,age=60):
    t=NOW-timedelta(seconds=age)
    r={"event_id":"test","league":"bundesliga","home":"H","away":"A",
       "kickoff_utc_recorded":(NOW+timedelta(seconds=lead)).isoformat(),
       "source_prediction_utc":t.isoformat(),"source_projection_sha256":"0"*64,
       "source_model":"poisson-shrinkage-unvalidated-v4.1",
       "expected_home_goals":1.5,"expected_away_goals":1.,
       "derived_rho0":summary(grid(0,0,1.5,1.))["1x2"]}
    return {"source_as_of_utc":t.isoformat(),"predictions":[r],"exclusions":{}}
class ForwardTests(unittest.TestCase):
    def test_output_is_research_only(self):
        r=forward({}, "0"*64,clock=lambda:NOW,upstream=lambda _:source())
        self.assertEqual(r["predictions_count"],1)
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertFalse(r["v5_ensemble_live_integration"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_stale_or_close(self):
        for s in (source(lead=600),source(age=36001)):
            self.assertEqual(forward({}, "0"*64,clock=lambda:NOW,upstream=lambda _:s)["predictions_count"],0)
    def test_end_clock_recheck(self):
        t=iter([NOW,NOW+timedelta(seconds=500)])
        r=forward({}, "0"*64,clock=lambda:next(t),upstream=lambda _:source(lead=1000))
        self.assertEqual(r["predictions_count"],0)
    def test_mismatch(self):
        s=source();s["predictions"][0]["derived_rho0"]=[1.,0.,0.]
        r=forward({}, "0"*64,clock=lambda:NOW,upstream=lambda _:s)
        self.assertEqual(r["predictions_count"],0)
