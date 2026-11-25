import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_correction_review import review_correction, review_digest, review_stoppage
from test_live_snapshot_commitment import envelope, NOW


def package(kind="GOAL_CANCELLED"):
    env=envelope()
    column="home" if kind=="GOAL_CANCELLED" else "red_home"
    for key in ("previous_a","previous_b"):
        env[key][column]=1
    events=[dict(origin=env[key]["origin"],fixture_id=env[key]["fixture_id"],
                 kind=kind,side="HOME",event_ref="event-"+key,
                 observed=NOW-30,received=NOW-25) for key in ("a","b")]
    return dict(envelope=env,events=events)


class CorrectionReviewTests(unittest.TestCase):
    def audit(self,p,reason,digest=None):
        out=review_correction(p,review_digest(p) if digest is None else digest,NOW)
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["reason"],reason)
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertFalse(out["positive_ev_verified"])
        self.assertFalse(out["source_authenticated"])
        return out

    def test_consistent_goal_and_red_claims_never_resume(self):
        for kind in ("GOAL_CANCELLED","RED_RESCINDED"):
            p=package(kind)
            out=self.audit(p,"CONSISTENT_CORRECTION_CLAIMS_PENDING_REVIEW")
            self.assertTrue(out["correction_review_only"])
            self.assertFalse(out["correction_authenticated"])
            self.assertFalse(out["forecast_resume_allowed"])
            self.assertNotIn("fulltime_probabilities",out)

    def test_commitment_mutation(self):
        p=package()
        d=review_digest(p)
        p["events"][0]["event_ref"]="changed"
        self.audit(p,"CORRECTION_COMMITMENT_MISMATCH",d)

    def test_missing_claim(self):
        p=package()
        p["events"].pop()
        self.audit(p,"TWO_CORRECTION_CLAIMS_REQUIRED")

    def test_duplicate_origin(self):
        p=package()
        p["events"][1]["origin"]=p["events"][0]["origin"]
        self.audit(p,"DUPLICATE_CORRECTION_ORIGIN")

    def test_wrong_origin(self):
        p=package()
        p["events"][0]["origin"]="unrelated"
        self.audit(p,"CORRECTION_ORIGIN_MISMATCH")

    def test_disagreeing_claim(self):
        p=package()
        p["events"][1]["side"]="AWAY"
        self.audit(p,"CORRECTION_EVENT_CONFLICT")

    def test_wrong_fixture(self):
        p=package()
        for e in p["events"]:
            e["fixture_id"]="wrong"
        self.audit(p,"CORRECTION_CLOCK_OR_FIXTURE_MISMATCH")

    def test_claim_after_snapshot(self):
        p=package()
        p["events"][0]["received"]=NOW+1
        self.audit(p,"CORRECTION_CLOCK_OR_FIXTURE_MISMATCH")

    def test_claim_before_history(self):
        p=package()
        p["events"][0]["observed"]=NOW-100
        self.audit(p,"CORRECTION_CLOCK_OR_FIXTURE_MISMATCH")

    def test_impossible_delta(self):
        p=package()
        for k in ("previous_a","previous_b"):
            p["envelope"][k]["home"]=2
        self.audit(p,"CORRECTION_DELTA_MISMATCH")

    def test_history_conflict(self):
        p=package()
        p["envelope"]["previous_b"]["home"]=0
        self.audit(p,"CORRECTION_HISTORY_CONFLICT")

    def test_replay(self):
        p=package()
        p["envelope"]["previous_a"]["received"]=p["envelope"]["a"]["received"]
        self.audit(p,"CORRECTION_HISTORY_REPLAY")

    def test_unsupported_event(self):
        p=package()
        for e in p["events"]:
            e["kind"]="UNKNOWN"
        self.audit(p,"UNSUPPORTED_CORRECTION")

    def test_stoppage_minimum_not_end_time(self):
        for elapsed,minimum,expected in ((60,4,180),(240,4,0),(360,4,0)):
            out=review_stoppage(elapsed,minimum)
            self.assertEqual(out["status"],"HOLD")
            self.assertEqual(out["claimed_minimum_remaining_seconds"],expected)
            self.assertFalse(out["final_whistle_verified"])
            self.assertFalse(out["forecast_resume_allowed"])

    def test_unknown_or_invalid_stoppage(self):
        self.assertEqual(review_stoppage(0,None)["reason"],"STOPPAGE_MINIMUM_UNKNOWN")
        for elapsed,minimum in ((True,4),(-1,4),(0,True),(0,-1),(0,61)):
            self.assertEqual(review_stoppage(elapsed,minimum)["status"],"HOLD")
            self.assertNotIn("claimed_minimum_remaining_seconds",review_stoppage(elapsed,minimum))

if __name__=="__main__":
    unittest.main()
