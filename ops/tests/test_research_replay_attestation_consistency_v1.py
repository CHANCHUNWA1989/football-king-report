import hashlib
import unittest
from ops.research_quote_archive_v1 import _canonical
from ops.research_historic_replay_policy_v1 import verify_historical_replay_plan,REQUIRED_CONTROLS

def plan(attestation):
    p={"schema":"football-king-historic-replay-plan-v1","status":"HOLD",
       "production_recommendations":"DISABLED","execution_permitted":False,
       "executor_configured":False,"qualified_for_production":False,
       "attestation":attestation,"required_controls":dict(REQUIRED_CONTROLS),
       "reason":("SOURCE_BYTES_MATCH_BUT_SANDBOX_NOT_CONFIGURED"
                 if attestation["historic_source_bytes_matched"]
                 else "SOURCE_ATTESTATION_FAILED")}
    return resign(p)

def resign(p):
    p["sha256"]=hashlib.sha256(_canonical({k:v for k,v in p.items()
                                           if k!="sha256"}).encode()).hexdigest()
    return p

def attested(matched=True):
    return {"status":"HOLD","production_recommendations":"DISABLED",
            "qualified_for_production":False,"execution_permitted":False,
            "historic_replay_verified":False,
            "historic_source_bytes_matched":matched,
            "reason":("HISTORIC_SOURCE_BYTES_MATCH" if matched
                      else "HISTORIC_SOURCE_MISMATCH")}

class ReplayAttestationConsistencyTests(unittest.TestCase):
    def test_matched_attestation(self):
        self.assertTrue(verify_historical_replay_plan(plan(attested())))
    def test_failed_attestation(self):
        self.assertTrue(verify_historical_replay_plan(plan(attested(False))))
    def test_forged_reason_recomputed_hash(self):
        p=plan(attested())
        p["reason"]="SOURCE_ATTESTATION_FAILED"
        self.assertFalse(verify_historical_replay_plan(resign(p)))
    def test_forged_attestation_recomputed_hash(self):
        p=plan(attested())
        p["attestation"]["historic_replay_verified"]=True
        self.assertFalse(verify_historical_replay_plan(resign(p)))
    def test_forged_success_recomputed_hash(self):
        p=plan(attested(False))
        p["attestation"]["historic_source_bytes_matched"]=True
        self.assertFalse(verify_historical_replay_plan(resign(p)))
if __name__=="__main__":unittest.main()
