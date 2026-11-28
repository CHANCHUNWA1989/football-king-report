import copy
import unittest
from ops.model_divergence_guard import audit


class DivergenceTests(unittest.TestCase):
    def setUp(self):
        self.a = dict(event_id='synthetic:1', league='epl', home_id='h', away_id='a', model_id='A', kickoff_utc='2026-11-29T01:30:00+08:00', information_cutoff_utc='2026-11-28T09:00:00Z', prediction_utc='2026-11-28T09:30:00Z', p=[.45,.24,.31])
        self.b = dict(self.a, model_id='B', p=[.44,.24,.32])
    def check(self, **changes):
        b = dict(self.b, **changes)
        before = copy.deepcopy((self.a,b))
        r = audit(self.a,b,as_of_utc='2026-11-28T12:00:00Z')
        self.assertEqual((self.a,b),before)
        self.assertEqual(r['production_recommendations'],'DISABLED')
        self.assertFalse(r['can_recommend_bets'])
        return r
    def test_close(self): self.assertEqual(self.check()['status'],'RESEARCH_ONLY')
    def test_opposite(self): self.assertEqual(self.check(p=[.33,.24,.43])['reason'],'DIRECTION_CONFLICT')
    def test_large_gap(self): self.assertEqual(self.check(p=[.55,.24,.21])['reason'],'LARGE_GAP')
    def test_tie(self): self.assertEqual(self.check(p=[.38,.24,.38])['status'],'HOLD')
    def test_invalid(self):
        for changes in [dict(event_id='synthetic:2'),dict(home_id='a',away_id='h'),dict(league='other'),dict(kickoff_utc='2026-11-28T18:30:00Z'),dict(information_cutoff_utc='2026-11-28T09:01:00Z'),dict(prediction_utc='2026-11-28T12:01:00Z'),dict(prediction_utc='2026-11-28T08:59:00Z'),dict(prediction_utc='2026-11-28T09:30:00'),dict(model_id='A'),dict(p=[True,0,0]),dict(p=[float('nan'),.3,.7]),dict(p=[.4,.4,.4]),dict(p=[-1,1,1]),dict(p=[1,0]),dict(home_id='h',away_id='h'),dict(information_cutoff_utc='2026-11-27T09:00:00Z')]:
            with self.subTest(changes=changes):
                r=self.check(**changes)
                self.assertEqual(r['status'],'HOLD')
                self.assertIsNone(r['max_gap'])
    def test_kickoff(self):
        self.assertEqual(audit(self.a,self.b,as_of_utc='2026-11-28T17:30:00Z')['status'],'HOLD')
    def test_missing(self):
        self.assertEqual(audit(self.a,None,as_of_utc='2026-11-28T12:00:00Z')['status'],'HOLD')

if __name__ == '__main__': unittest.main()
