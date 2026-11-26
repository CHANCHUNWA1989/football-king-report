import unittest
from ops.v19_evidence_index import index,safe,metric,SCHEMAS
from ops import v8_multiseason as v

def report(schema,**k):
    return {"schema":schema,"status":"HOLD","production_recommendations":"DISABLED",
            "verified_forward_sample_credit":0,"automatic_promotion":False,**k}
def m(n):
    return {"n":n,"correct":n//2,"log_loss":1.,"brier":.6}
def fixture():
    n=140;latest=210;ucl=1536
    models=report(SCHEMAS["models"],pooled={"common_n":n,"all_finished":latest})
    models.update(
        v10_causal_experts=report("v10-causal-eight-expert-research-v1",assessment_n=n,pooled={"same_fixture_metrics":{"candidate":m(n)}}),
        v10_1_stacking=report("v10-1-chronological-stacking-research-v1",assessment_n=n,pooled={"metrics":{"stack":m(n)}}),
        v11_bayesian_state=report("v11-dynamic-gamma-poisson-research-v1",common_n=n,same_fixture_metrics={"bayes":m(n)}),
        v11_3_context_moe=report("v11-3-context-gated-nine-expert-research-v1",assessment_n=n,pooled={"metrics":{"moe":m(n)}}),
        v17_selective_confidence=report("v17-domestic-selective-confidence-research-v1",assessment_eligible_n=n,
            assessment_all_finished=latest,assessment_selected={"n":0,"correct":0},chosen_rule=None),
        v18_model_competition=report("v18-causal-model-competition-research-v1",assessment_n=n,
            pooled={"n":n,"metrics":{"stack":m(n),"competition":m(n)}},
            per_league={k:{"n":20} for k in v.LEAGUES}))
    u={"historical_phase_matches":ucl}
    a={"dynamic_goal_strength_challenger":report("ucl-dynamic-country-club-goal-strength-research-v1",assessment_n=144,metrics={"candidate":m(144)}),
       "v15_draw_hurdle":report("v15-ucl-draw-hurdle-research-v1",assessment_n=144,metrics={"candidate":m(144)},
        v16_unified_probability=report("v16-unified-outcome-mass-research-v1",assessment_n=144,metrics={"hurdle_reconciled":{"one_x_two":m(144)}}))}
    h=report(SCHEMAS["history"],historical_domestic_finished=29207,previous_domestic_finished=11946,
        new_domestic_finished=17261,ucl_historical_finished_reference=ucl,combined_historical_finished=30743,
        combined_history_target_30000=True,rolling_all={"n":25000,"baseline":m(25000),"candidate":m(25000)},
        latest_season={"n":latest,"baseline":m(latest),"candidate":m(latest)},quarantined_scopes=[])
    market=report(SCHEMAS["market"],raw_n=128,eligible_research_n=128,
        v14_consensus_calibration=report("v14-consensus-calibration-research-v1",development_n=58,assessment_n=55,embargo_excluded_n=15))
    return {"domestic":{"history_finished":11946},"ucl_archive":u,"ucl_adaptive":a,"models":models,"history":h,
            "market":market,"schedule":report(SCHEMAS["schedule"],assessment_n=latest)}

class EvidenceIndexTests(unittest.TestCase):
    def test_complete_archive_is_not_release(self):
        r=index(fixture())
        self.assertEqual(r["historical_archive"]["combined"],30743)
        self.assertTrue(r["historical_archive"]["raw_archive_target_30000"])
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
    def test_missing_nested_stage(self):
        r=fixture();del r["models"]["v18_model_competition"]
        with self.assertRaises(KeyError):index(r)
    def test_inconsistent_count_and_credit(self):
        r=fixture();r["history"]["combined_historical_finished"]+=1
        with self.assertRaisesRegex(ValueError,"COUNT_CONFLICT"):index(r)
        r=fixture();r["models"]["v17_selective_confidence"]["verified_forward_sample_credit"]=1
        with self.assertRaisesRegex(ValueError,"UNSAFE_STAGE"):index(r)
    def test_projection_mismatch(self):
        r=fixture();r["ucl_adaptive"]["v15_draw_hurdle"]["v16_unified_probability"]["metrics"]["hurdle_reconciled"]["one_x_two"]["correct"]+=1
        with self.assertRaisesRegex(ValueError,"PROJECTION_CONFLICT"):index(r)
    def test_invalid_metrics_and_unsafe_flag(self):
        with self.assertRaisesRegex(ValueError,"METRIC"):metric(dict(m(100),log_loss=float("nan")),100)
        with self.assertRaisesRegex(ValueError,"UNSAFE_STAGE"):safe(report("test",automatic_promotion=True),"test")
