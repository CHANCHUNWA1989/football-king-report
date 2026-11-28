import copy
import unittest
from datetime import date,datetime,timedelta,timezone
from ops.shadow_forecast import predict_league
from ops.opponent_forward_capture import capture,attach,TOP_KEY


class OpponentForwardCaptureTest(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,28,0,0,tzinfo=timezone.utc)
        self.records=[]
        for i in range(60):
            d=date.fromordinal(date(2026,8,1).toordinal()+i)
            h,a=("Alpha","Beta") if i%2==0 else ("Beta","Alpha")
            self.records.append({"league":"epl","date":d.isoformat(),"home":h,"away":a,
                "score_ft":[2,1],"status":"FINISHED"})
        future={"date":"2026-11-28","home":"Alpha","away":"Beta","status":"SCHEDULED",
                "event_id":"synthetic:1","kickoff_utc":"2026-11-28T00:25:00+00:00"}
        rows=predict_league(self.records+[future],"epl",self.now)
        self.assertEqual(len(rows),1)
        self.shadow={"schema":"football-king-uncalibrated-shadow-1","status":"SHADOW_ONLY",
            "production_recommendations":"DISABLED","as_of_utc":self.now.isoformat(),
            "predictions_count":1,"predictions":rows}
        self.finished={"schema":"football-king-single-source-finished-results-1",
            "captured_utc":self.now.isoformat(),"production_recommendations":"DISABLED",
            "records":self.records}
    def run_capture(self,minutes):
        clock=iter([self.now,self.now+timedelta(minutes=minutes)])
        return capture(self.shadow,self.finished,lambda:next(clock))
    def test_capture_and_attach_preserve_original(self):
        rec=self.run_capture(2)
        self.assertEqual(rec["predictions_count"],1)
        self.assertEqual(rec["status"],"FORWARD_RESEARCH_CAPTURE_ONLY")
        self.assertEqual(rec["predictions"][0]["candidate_prediction_utc"],rec["generated_utc"])
        self.assertNotEqual(rec["generated_utc"],self.shadow["as_of_utc"])
        original=copy.deepcopy(self.shadow)
        attached=attach(self.shadow,rec)
        self.assertEqual(self.shadow,original)
        self.assertEqual(attached.pop(TOP_KEY),original)
        self.assertFalse(rec["independently_verified"])
    def test_completion_buffer_and_rewound_clock(self):
        for minutes in (15,26,31,-1):
            with self.subTest(minutes=minutes):
                rec=self.run_capture(minutes)
                self.assertEqual(rec["status"],"HOLD")
                self.assertEqual(rec["predictions_count"],0)
    def test_tamper_or_prior_capture(self):
        rec=self.run_capture(2)
        bad=copy.deepcopy(self.shadow)
        bad["predictions"][0]["p_home"]=.99
        with self.assertRaises(ValueError):
            attach(bad,rec)
        with self.assertRaises(ValueError):
            attach(attach(self.shadow,rec),rec)
    def test_unsafe_capture(self):
        rec=self.run_capture(2)
        rec["positive_ev_verified"]=True
        with self.assertRaises(ValueError):
            attach(self.shadow,rec)


if __name__=="__main__":
    unittest.main()
