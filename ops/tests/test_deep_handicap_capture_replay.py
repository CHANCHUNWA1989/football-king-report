import copy
import unittest
from datetime import timedelta
from test_deep_handicap_private_capture import inputs,NOW
from deep_handicap_private_capture import capture,_digest
from deep_handicap_capture_replay import replay_and_evaluate

class DeepCaptureReplayTests(unittest.TestCase):
    def setup_case(self):
        s,q=inputs();sealed=capture(s,q,now=NOW)
        self.assertIsNotNone(sealed["candidate"])
        c=sealed["candidate"]
        ident={k:c[k] for k in ("league_id","fixture_id","home_id","away_id","kickoff_utc")}
        results=[dict(ident,provider_id=p,evidence_reference="synthetic",
                      status="FINISHED_90_MINUTES",captured_utc=(NOW+timedelta(hours=4)).isoformat(),score_ft=[2,0])
                 for p in ("source1","source2")]
        return s,q,sealed,results

    def audit(self,s,q,c,r):
        return replay_and_evaluate(s,q,c,r,as_of_utc=(NOW+timedelta(hours=5)).isoformat())

    def test_private_replay_then_half_loss_without_mutating_capture(self):
        s,q,c,r=self.setup_case();before=copy.deepcopy((s,q,c,r))
        report=self.audit(s,q,c,r)
        self.assertTrue(report["locally_replayed"])
        self.assertEqual(report["reason"],"LOCAL_REPLAY_AND_STRUCTURAL_SETTLEMENT")
        cohort=report["evaluation"]["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]
        self.assertEqual(cohort["grades"]["HALF_LOSS"],1)
        self.assertEqual(report["authenticated_forward_samples"],0)
        self.assertEqual((s,q,c,r),before)

    def test_rehashed_tampering_does_not_pass_replay(self):
        s,q,c,r=self.setup_case()
        c["candidate"]["challenger"]["model_id"]="changed"
        c["candidate_sha256"]=_digest(c["candidate"])
        self.assertFalse(self.audit(s,q,c,r)["locally_replayed"])

    def test_changed_quote_input_and_conflicting_results(self):
        s,q,c,r=self.setup_case()
        q2=copy.deepcopy(q);q2["quotes"][0]["decimal_odds"]=2.1
        self.assertFalse(self.audit(s,q2,c,r)["locally_replayed"])
        r[1]["score_ft"]=[3,0]
        report=self.audit(s,q,c,r)
        self.assertTrue(report["locally_replayed"])
        self.assertEqual(report["reason"],"RESULT_CLAIMS_REJECTED")
        self.assertEqual(report["evaluation"]["true_forward_sample_count"],0)
