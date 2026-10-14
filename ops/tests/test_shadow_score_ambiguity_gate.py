import unittest
from shadow_score_ambiguity_gate import triage

def data(first,second):
    return {"status":"HOLD","independently_verified":False,"eligible_for_model_scoring":False,
            "fixtures":[{"fixture_id":"one","provider_diagnostics":{
                "DFB":{"plausible_score_like_tokens":first},
                "NDR":{"plausible_score_like_tokens":second}}}]}

class AmbiguityTests(unittest.TestCase):
    def test_unique_agreement_still_unverified(self):
        x=triage(data([[2,1]],[[2,1]]))
        self.assertEqual(x["fixtures"][0]["ambiguity"],"ONE_SHARED_TOKEN_NOT_FT")
        self.assertFalse(x["fixtures"][0]["eligible_for_model_scoring"])
    def test_multiple_context_scores_blocked(self):
        x=triage(data([[2,1],[0,2]],[[2,1],[1,1]]))
        self.assertEqual(x["fixtures"][0]["ambiguity"],"MULTIPLE_POSSIBLE_SCORES")
    def test_no_shared_candidate(self):
        self.assertEqual(triage(data([[2,1]],[[1,0]]))["fixtures"][0]["ambiguity"],"NO_SHARED_CANDIDATE")
    def test_unsafe_input(self):
        x=data([],[])
        x["independently_verified"]=True
        with self.assertRaises(ValueError):triage(x)
    def test_invalid_score(self):
        with self.assertRaises(ValueError):triage(data([[99,0]],[[1,0]]))
if __name__=="__main__":unittest.main()
