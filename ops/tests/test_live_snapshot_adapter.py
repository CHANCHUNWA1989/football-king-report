import unittest
import sys
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_snapshot_adapter import check, research_predict
from test_inplay_state_challenger_vnext import sample

NOW = int(datetime(2026,11,3,21,5,tzinfo=timezone.utc).timestamp())
A = dict(fixture_id='synthetic-ucl-001',origin='A',observed=NOW-10,received=NOW-5,minute=50,home=0,away=2,red_home=0,red_away=0,phase='SECOND_HALF')
B = dict(A,origin='B',observed=NOW-8)
M = dict(fixture_id=A['fixture_id'],minute_elapsed=50,score_home=0,score_away=2,red_home=0,red_away=0,decision_utc='2026-11-03T21:05:00Z')

class GuardTests(unittest.TestCase):
    def test_cases(self):
        cases = [(A,B,M,None,'CONSISTENT'),(A,dict(B,origin='A'),M,None,'IDENTITY_OR_ORIGIN'),(A,dict(B,observed=NOW-91),M,None,'STALE_OR_FUTURE'),(A,dict(B,received=NOW+1),M,None,'STALE_OR_FUTURE'),(A,dict(B,observed=NOW-45),M,None,'UNSYNCED'),(A,dict(B,minute=51),M,None,'STATE_CONFLICT'),(A,dict(B,red_home=1),M,None,'STATE_CONFLICT'),(A,dict(B,home=1),M,None,'STATE_CONFLICT'),(A,dict(B,phase='HALFTIME'),M,None,'INVALID'),(A,B,M,dict(A,home=1),'ROLLBACK_OR_CORRECTION_REVIEW'),(A,B,dict(M,score_home=1),None,'MODEL_STATE_MISMATCH'),(A,B,dict(M,red_home=False),None,'MODEL_STATE_MISMATCH'),(A,B,dict(M,decision_utc='2026-11-03T21:05:01Z'),None,'DECISION_MISMATCH'),(A,B,{},None,'INVALID_MODEL'),(A,dict(B,received=NOW-20),M,None,'INVALID'),(A,B,M,dict(A,red_home=1),'ROLLBACK_OR_CORRECTION_REVIEW')]
        for a,b,m,p,r in cases:
            with self.subTest(reason=r):
                self.assertEqual(check(a,b,m,NOW,p),r)
                if r != 'CONSISTENT':
                    o=research_predict(a,b,m,NOW,p)
                    self.assertEqual(o['status'],'HOLD')
                    self.assertEqual(o['production_recommendations'],'DISABLED')
                    self.assertFalse(o['positive_ev_verified'])

    def test_real_parent_model(self):
        m=sample(minute=50,decision=M['decision_utc'])
        o=research_predict(A,B,m,NOW)
        self.assertEqual(o['status'],'RESEARCH_ONLY')
        self.assertAlmostEqual(sum(o['fulltime_probabilities'].values()),1.0)
        self.assertEqual(o['production_recommendations'],'DISABLED')
        self.assertFalse(o['source_independence_verified'])
        self.assertFalse(o['positive_ev_verified'])
        m['event_consensus']['score_home']=1
        self.assertEqual(research_predict(A,B,m,NOW)['status'],'HOLD')

if __name__ == '__main__': unittest.main()
