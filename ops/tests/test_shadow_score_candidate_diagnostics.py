import unittest
from shadow_score_candidate_diagnostics import diagnose

class DiagnosticsTests(unittest.TestCase):
    def test_timestamp_and_score_remain_unverified(self):
        probe={"status":"HOLD","independently_verified":False,"eligible_for_model_scoring":False,
               "both_sources_name_overlap_fixture_ids":["a"],"source_probes":[
               {"provider":"DFB","fixture_text_checks":[{"fixture_id":"a","score_like_tokens_unverified":[
               {"home_goals_candidate":18,"away_goals_candidate":30},
               {"home_goals_candidate":2,"away_goals_candidate":1}]}]},
               {"provider":"NDR","fixture_text_checks":[{"fixture_id":"a","score_like_tokens_unverified":[
               {"home_goals_candidate":2,"away_goals_candidate":1}]}]}]}
        out=diagnose(probe)
        self.assertEqual(out["fixture_count"],1)
        self.assertEqual(out["fixtures"][0]["provider_diagnostics"]["DFB"]["plausible_score_like_tokens"],[[2,1]])
        self.assertFalse(out["independently_verified"])
        self.assertFalse(out["fixtures"][0]["eligible_for_model_scoring"])
    def test_unsafe_probe_rejected(self):
        with self.assertRaises(ValueError):
            diagnose({"status":"HOLD","independently_verified":True,"eligible_for_model_scoring":False})
    def test_duplicate_provider_rejected(self):
        with self.assertRaises(ValueError):
            diagnose({"status":"HOLD","independently_verified":False,"eligible_for_model_scoring":False,
                      "source_probes":[{"provider":"DFB"},{"provider":"DFB"}]})
if __name__=="__main__":unittest.main()
