import unittest
from sealed_ft_candidate_linkage import link

class LinkTests(unittest.TestCase):
    def test_empty(self):
        d = {'schema':'football-king-cross-source-ft-diagnostic-v1','independently_verified':False,'external_provenance_rechecked':False,'production_recommendations':'DISABLED','agreements':[]}
        result = link([], d)
        self.assertEqual(result['candidate_link_count'], 0)
        self.assertFalse(result['eligible_for_model_scoring'])

    def test_matching_fixture_is_candidate_not_verified(self):
        d = {'schema':'football-king-cross-source-ft-diagnostic-v1','independently_verified':False,'external_provenance_rechecked':False,'production_recommendations':'DISABLED',
             'agreements':[{'match_date':'2026-10-15','home':'Home FC','away':'Away FC','openliga_score':[2,1],'openfootball_score':[2,1]}]}
        sealed=[{'fixture_id':'fx-1','kickoff_utc':'2026-10-15T18:00:00Z','home':'Home FC','away':'Away FC','production_recommendations':'DISABLED'}]
        r=link(sealed,d)
        self.assertEqual(r['candidate_link_count'],1)
        self.assertFalse(r['eligible_for_model_scoring'])
        self.assertFalse(r['links'][0]['independently_verified'])
        self.assertEqual(r['links'][0]['link_status'],'CANDIDATE_ONLY')

    def test_date_mismatch_diagnostic(self):
        d={'schema':'football-king-cross-source-ft-diagnostic-v1','independently_verified':False,'external_provenance_rechecked':False,'production_recommendations':'DISABLED',
           'agreements':[{'match_date':'2026-10-15','home':'Home FC','away':'Away FC','openliga_score':[2,1],'openfootball_score':[2,1]}]}
        sealed=[{'fixture_id':'fx-1','kickoff_utc':'2026-10-14T18:00:00Z','home':'Home FC','away':'Away FC','production_recommendations':'DISABLED'}]
        r=link(sealed,d)
        self.assertEqual(r['candidate_link_count'],0)
        self.assertEqual(r['link_blockers']['NO_ARCHIVED_FIXTURE_ON_DATE'],1)

    def test_ambiguous_duplicate_archive_is_refused(self):
        d={'schema':'football-king-cross-source-ft-diagnostic-v1','independently_verified':False,'external_provenance_rechecked':False,'production_recommendations':'DISABLED',
           'agreements':[{'match_date':'2026-10-15','home':'Home FC','away':'Away FC','openliga_score':[2,1],'openfootball_score':[2,1]}]}
        row={'fixture_id':'fx-1','kickoff_utc':'2026-10-15T18:00:00Z','home':'Home FC','away':'Away FC','production_recommendations':'DISABLED'}
        r=link([row,row],d)
        self.assertEqual(r['candidate_link_count'],0)
        self.assertEqual(r['link_blockers']['AMBIGUOUS_SEALED_FIXTURE'],1)

    def test_team_mismatch_diagnostic(self):
        d={'schema':'football-king-cross-source-ft-diagnostic-v1','independently_verified':False,'external_provenance_rechecked':False,'production_recommendations':'DISABLED',
           'agreements':[{'match_date':'2026-10-15','home':'Different FC','away':'Away FC','openliga_score':[2,1],'openfootball_score':[2,1]}]}
        sealed=[{'fixture_id':'fx-1','kickoff_utc':'2026-10-15T18:00:00Z','home':'Home FC','away':'Away FC','production_recommendations':'DISABLED'}]
        r=link(sealed,d)
        self.assertEqual(r['candidate_link_count'],0)
        self.assertEqual(r['link_blockers']['NO_EXACT_TEAM_PAIR'],1)

    def test_disagreeing_scores_never_link(self):
        d={'schema':'football-king-cross-source-ft-diagnostic-v1','independently_verified':False,'external_provenance_rechecked':False,'production_recommendations':'DISABLED',
           'agreements':[{'match_date':'2026-10-15','home':'Home FC','away':'Away FC','openliga_score':[2,1],'openfootball_score':[1,2]}]}
        sealed=[{'fixture_id':'fx-1','kickoff_utc':'2026-10-15T18:00:00Z','home':'Home FC','away':'Away FC','production_recommendations':'DISABLED'}]
        r=link(sealed,d)
        self.assertEqual(r['candidate_link_count'],0)
        self.assertFalse(r['eligible_for_model_scoring'])

if __name__ == '__main__':
    unittest.main()
