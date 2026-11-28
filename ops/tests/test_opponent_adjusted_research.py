import copy
import unittest
from datetime import date,datetime,timezone
from ops.opponent_adjusted_research import history_before,fit,rates,replay,metrics,build
from ops.shadow_forecast import predict_league


class OpponentAdjustedTest(unittest.TestCase):
    def setUp(self):
        self.rows=[]
        for i in range(60):
            d=date.fromordinal(date(2026,8,1).toordinal()+i)
            h,a=("Alpha","Beta") if i%2==0 else ("Beta","Alpha")
            self.rows.append({"league":"epl","date":d.isoformat(),"home":h,"away":a,
                              "score_ft":[2 if h=="Alpha" else 0,1 if a=="Alpha" else 0],
                              "status":"FINISHED"})
        self.day=date(2026,11,1)
    def test_strength_and_determinism(self):
        h=history_before(self.rows,"epl",self.day)
        m=fit(h,self.day)
        self.assertEqual(m,fit(h,self.day))
        a,b=rates(m,"Alpha","Beta")
        self.assertGreater(a,b)
        self.assertIsNone(rates(m,"Unknown","Beta"))
    def test_no_future_or_same_day(self):
        h=history_before(self.rows,"epl",self.day)
        more=self.rows+[dict(self.rows[0],date=self.day.isoformat(),score_ft=[20,0]),
                        dict(self.rows[0],date="2026-12-01",score_ft=[20,0])]
        self.assertEqual(h,history_before(more,"epl",self.day))
        self.assertIsNone(fit(h,self.rows and date(2026,8,1)))
    def test_duplicate_and_conflict(self):
        self.assertEqual(history_before(self.rows,"epl",self.day),
            history_before(self.rows+[copy.deepcopy(self.rows[0])],"epl",self.day))
        with self.assertRaises(ValueError):
            history_before(self.rows+[dict(self.rows[0],score_ft=[0,9])],"epl",self.day)
    def test_paired_replay(self):
        r=replay(self.rows,"epl")
        self.assertEqual(len(r),30)
        self.assertEqual(r[0]["training_games"],30)
        for x in r:
            self.assertAlmostEqual(sum(x["candidate"]),1,places=6)
        self.assertEqual(metrics(r,"original")["n"],metrics(r,"candidate")["n"])
    def test_same_day_outcome_not_used(self):
        r=replay(self.rows,"epl")
        changed=copy.deepcopy(self.rows)
        changed[-1]["score_ft"]=[20,20]
        s=replay(changed,"epl")
        self.assertEqual(r[-1]["candidate"],s[-1]["candidate"])
        self.assertEqual(r[-1]["original"],s[-1]["original"])
    def test_real_producer_training_identity_guard(self):
        now=datetime(2026,11,1,0,0,tzinfo=timezone.utc)
        future={"date":"2026-11-01","home":"Alpha","away":"Beta","status":"SCHEDULED",
                "event_id":"synthetic:identity","kickoff_utc":"2026-11-01T03:00:00+00:00"}
        preds=predict_league(self.rows+[future],"epl",now)
        self.assertEqual(len(preds),1)
        shadow={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
                "production_recommendations":"DISABLED","as_of_utc":now.isoformat(),
                "predictions_count":1,"predictions":preds}
        finished={"schema":"football-king-single-source-finished-results-1",
                  "captured_utc":now.isoformat(),"production_recommendations":"DISABLED",
                  "records":self.rows}
        out=build(shadow,finished,now)
        self.assertEqual(len(out["predictions"]),1)
        self.assertEqual(out["predictions"][0]["training_sha256"],preds[0]["training_observations_sha256"])
        changed=copy.deepcopy(finished)
        changed["records"][0]["score_ft"]=[19,0]
        self.assertFalse(build(shadow,changed,now)["predictions"])
        changed_shadow=copy.deepcopy(shadow)
        changed_shadow["predictions"][0]["p_home"]=.999
        self.assertFalse(build(changed_shadow,finished,now)["predictions"])

    def test_invalid_envelope_hold(self):
        out=build({}, {}, datetime(2026,11,1,tzinfo=timezone.utc))
        self.assertEqual(out["status"],"HOLD")
        self.assertEqual(out["production_recommendations"],"DISABLED")
        self.assertEqual(out["recommendation_count"],0)
        self.assertFalse(out["predictions"])


if __name__=="__main__":
    unittest.main()
