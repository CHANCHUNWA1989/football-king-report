import unittest
from shadow_pipeline_integrity import check

def fixture():
    archive=[{"fixture_id":"one"}]
    coverage={"status":"HOLD","production_recommendations":"DISABLED","independently_verified":False,"matured_unmatched_fixture_ids":["one"]}
    gaps={"status":"HOLD","production_recommendations":"DISABLED","independently_verified":False,"fixtures":[{"fixture_id":"one","eligible_for_model_scoring":False}]}
    probe={"status":"HOLD","production_recommendations":"DISABLED","independently_verified":False}
    ambiguity={"status":"HOLD","production_recommendations":"DISABLED","independently_verified":False,"fixture_count":0,"fixtures":[]}
    daily={"status":"SHADOW_ONLY","production_recommendations":"DISABLED","valid_fixtures":0,"models":{k:{"sample_size":0} for k in ("original","market","market_50","market_75")}}
    readiness={"status":"HOLD","production_recommendations":"DISABLED","independently_verified":False,"matured_awaiting_ft":1,"valid_scored_fixtures":0}
    return archive,coverage,gaps,probe,ambiguity,daily,readiness

class IntegrityTests(unittest.TestCase):
    def test_consistent_research_bundle(self):
        self.assertEqual(check(*fixture())["status"],"PASS")
    def test_unsealed_queue_rejected(self):
        d=list(fixture());d[0]=[]
        self.assertIn("UNSEALED_QUEUE_FIXTURE",check(*d)["errors"])
    def test_model_mismatch_rejected(self):
        d=list(fixture());d[5]["models"]["market"]["sample_size"]=1
        self.assertIn("FOUR_MODEL_SAMPLE_MISMATCH",check(*d)["errors"])
    def test_production_enable_rejected(self):
        d=list(fixture());d[3]["production_recommendations"]="ENABLED"
        self.assertEqual(check(*d)["status"],"FAIL")

if __name__=="__main__":unittest.main()
