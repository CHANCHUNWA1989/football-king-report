import unittest
from live_core_statsbomb_cohort import temporal_summary
class TemporalDescriptiveTests(unittest.TestCase):
    def test_fixed_split_attrition_and_exposure_weighting(self):
        planned=[("2022-11-20",1,1,2),("2022-11-21",2,1,2),("2022-12-03",3,1,2),("2022-12-04",4,1,2)]
        def row(day,minutes,xg):
            return dict(match_date=day,regulation_cards=1,elapsed_beyond_45_by_half=[3,6],
                        buckets=[dict(dismissals=[1,0],elapsed_minutes=minutes,xg=[xg,0],shots=[1,0])])
        result=temporal_summary(planned,[row("2022-11-20",10,.5),row("2022-11-21",20,.5),row("2022-12-03",15,.1)])
        self.assertFalse(result["model_calibrated"])
        self.assertFalse(result["causal_effect_estimated"])
        g=result["splits"]["group_stage"];k=result["splits"]["knockout_stage"]
        self.assertEqual(g["accepted"],2);self.assertEqual(k["rejected"],1)
        self.assertAlmostEqual(g["state_exposure"][0]["xg_per_90"][0],3)
        self.assertTrue(g["state_exposure"][0]["small_sample"])
    def test_missing_data_not_zero_rate(self):
        result=temporal_summary([("2022-12-03",1,1,2)],[])
        self.assertIsNone(result["splits"]["knockout_stage"]["mean_elapsed_beyond_45_by_half"])
        self.assertEqual(result["splits"]["knockout_stage"]["state_exposure"],[])
