import copy
import unittest
from ops.model_divergence_batch import evaluate, MAX_FIXTURES

NOW = '2026-11-28T12:00:00Z'


def row(event, model, p=None, **kw):
    return dict(dict(event_id=event, league='epl', home_id='h', away_id='a',
                     model_id=model, kickoff_utc='2026-11-28T17:30:00Z',
                     information_cutoff_utc='2026-11-28T09:00:00Z',
                     prediction_utc='2026-11-28T10:00:00Z',
                     p=p if p is not None else [.45,.24,.31]), **kw)


class BatchTests(unittest.TestCase):
    def call(self, ids, left, right, now=NOW):
        before = copy.deepcopy((ids,left,right))
        r = evaluate(ids,left,right,as_of_utc=now)
        self.assertEqual((ids,left,right),before)
        self.assertEqual(r['production_recommendations'],'DISABLED')
        self.assertFalse(r['can_recommend_bets'])
        self.assertFalse(r['source_authenticated'])
        return r

    def test_order_independent_complete(self):
        r=self.call(['a','b'],[row('b','A'),row('a','A')],[row('a','B'),row('b','B')])
        self.assertEqual(r['status'],'RESEARCH_ONLY')
        self.assertEqual(r['counts'],{'NO_LARGE_DISAGREEMENT':2})
        self.assertEqual([x['manifest_index'] for x in r['results']],[0,1])

    def test_conflict_and_missing(self):
        r=self.call(['a','b','c'],[row('a','A'),row('b','A')],[row('a','B',[.30,.24,.46]),row('b','B')])
        self.assertEqual(r['status'],'HOLD')
        self.assertEqual(r['counts'],{'DIRECTION_CONFLICT':1,'NO_LARGE_DISAGREEMENT':1,'MISSING_PAIR':1})

    def test_bad_cutoff(self):
        r=self.call(['a'],[row('a','A')],[row('a','B',information_cutoff_utc='2026-11-28T09:01:00Z')])
        self.assertEqual(r['counts'],{'INVALID_INPUT':1})

    def test_missing_clock_not_fabricated(self):
        b=row('a','B'); del b['information_cutoff_utc']
        self.assertEqual(self.call(['a'],[row('a','A')],[b])['counts'],{'INVALID_INPUT':1})

    def test_duplicate_and_unexpected_fail_entire_batch(self):
        a=row('a','A'); b=row('a','B')
        for ids,left,right in [(['a','a'],[a],[b]),(['a'],[a,a],[b]),(['a'],[a],[b,b]),(['a'],[a,row('other','A')],[b]),(['a'],[a],[b,row('other','B')])]:
            with self.subTest(ids=ids,left=len(left),right=len(right)):
                r=self.call(ids,left,right)
                self.assertEqual(r['reason'],'INVALID_BATCH')
                self.assertEqual(r['results'],[])

    def test_invalid_manifest_and_source(self):
        for ids,left,right in [([],[],[]),('a',[],[]),([True],[],[]),(['a']*(MAX_FIXTURES+1),[],[]),(['a'],[None],[]),(['a'],[{}],[]),(['a'],None,[])]:
            with self.subTest():
                self.assertEqual(self.call(ids,left,right)['reason'],'INVALID_BATCH')

    def test_post_kickoff(self):
        r=self.call(['a'],[row('a','A')],[row('a','B')],now='2026-11-28T17:30:00Z')
        self.assertEqual(r['counts'],{'INVALID_INPUT':1})

    def test_no_raw_data_in_results(self):
        r=self.call(['secret_fixture'],[row('secret_fixture','A',raw='secret_payload')],[row('secret_fixture','B')])
        self.assertNotIn('secret',str(r))

    def test_empty_sources_preserve_manifest(self):
        r=self.call(['a','b'],[],[])
        self.assertEqual(r['counts'],{'MISSING_PAIR':2})

    def test_invalid_now(self):
        self.assertEqual(self.call(['a'],[],[],now='bad')['reason'],'INVALID_BATCH')
