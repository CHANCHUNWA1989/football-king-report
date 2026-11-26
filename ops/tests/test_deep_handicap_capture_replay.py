import copy
import unittest
from datetime import timedelta
from test_deep_handicap_private_capture import inputs,NOW
from deep_handicap_private_capture import capture,_digest
from deep_handicap_capture_replay import replay_and_evaluate,audit_declared_cohort

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

    def test_cohort_declared_missing_results_and_maturity(self):
        s,q,c,r=self.setup_case()
        item={"shadow":s,"quote_report":q,"sealed":c,"results":None}
        early=audit_declared_cohort([item],as_of_utc=(NOW+timedelta(minutes=5)).isoformat())
        self.assertTrue(early["declared_roster_reconciled"])
        self.assertEqual(early["states"]["PENDING_MATURITY"],1)
        late=audit_declared_cohort([item],as_of_utc=(NOW+timedelta(hours=5)).isoformat())
        self.assertEqual(late["states"]["MATURE_WITHOUT_RESULT"],1)
        self.assertFalse(late["complete_attempt_denominator_verified"])
        self.assertFalse(late["selection_bias_ruled_out"])
        self.assertEqual(early["declared_roster_sha256"],late["declared_roster_sha256"])
        item["results"]=r
        settled=audit_declared_cohort([item],as_of_utc=(NOW+timedelta(hours=5)).isoformat())
        self.assertEqual(settled["states"]["SETTLED_LOCAL"],1)
        self.assertEqual(settled["evaluation"]["cohorts"]["EXTERNAL_UNAUTHENTICATED"]["overall"]["n"],1)
        self.assertEqual(settled["authenticated_forward_samples"],0)
        self.assertEqual(settled["declared_roster_sha256"],late["declared_roster_sha256"])

    def test_cohort_rejects_duplicate_even_with_different_result_status(self):
        s,q,c,r=self.setup_case()
        item={"shadow":s,"quote_report":q,"sealed":c,"results":r}
        second=dict(item,results=None)
        report=audit_declared_cohort([item,second],as_of_utc=(NOW+timedelta(hours=5)).isoformat())
        self.assertFalse(report["declared_roster_reconciled"])
        self.assertIsNone(report["evaluation"])

    def test_cohort_invalid_capture_and_conflicting_results(self):
        s,q,c,r=self.setup_case()
        item={"shadow":s,"quote_report":q,"sealed":c,"results":r}
        r[1]["score_ft"]=[3,0]
        report=audit_declared_cohort([item],as_of_utc=(NOW+timedelta(hours=5)).isoformat())
        self.assertTrue(report["declared_roster_reconciled"])
        self.assertEqual(report["states"]["RESULT_CLAIMS_REJECTED"],1)
        self.assertEqual(report["states"]["SETTLED_LOCAL"],0)
        q["quotes"][0]["decimal_odds"]=2.1
        report=audit_declared_cohort([item],as_of_utc=(NOW+timedelta(hours=5)).isoformat())
        self.assertFalse(report["declared_roster_reconciled"])
        self.assertIsNone(report["evaluation"])

    def test_cohort_duplicate_market_or_same_pair_under_new_ids(self):
        s,q,c,r=self.setup_case()
        first={"shadow":s,"quote_report":q,"sealed":c,"results":None}
        s2,q2=copy.deepcopy((s,q))
        s2["predictions"][0]["event_id"]="source:43"
        # Same market ID, but a different claimed shadow ID.
        second={"shadow":s2,"quote_report":q2,"sealed":capture(s2,q2,now=NOW),"results":None}
        self.assertIsNotNone(second["sealed"]["candidate"])
        for candidate in (second,):
            report=audit_declared_cohort([first,candidate],as_of_utc=(NOW+timedelta(hours=5)).isoformat())
            self.assertFalse(report["declared_roster_reconciled"])
        for quote in q2["quotes"]:quote["event_id"]="other-market"
        second["sealed"]=capture(s2,q2,now=NOW)
        self.assertIsNotNone(second["sealed"]["candidate"])
        report=audit_declared_cohort([first,second],as_of_utc=(NOW+timedelta(hours=5)).isoformat())
        self.assertFalse(report["declared_roster_reconciled"])
