import unittest
from sealed_ft_candidate_linkage import link

class LinkTests(unittest.TestCase):
    def test_empty(self):
        d = {'schema':'football-king-cross-source-ft-diagnostic-v1','independently_verified':False,'external_provenance_rechecked':False,'production_recommendations':'DISABLED','agreements':[]}
        result = link([], d)
        self.assertEqual(result['candidate_link_count'], 0)
        self.assertFalse(result['eligible_for_model_scoring'])

if __name__ == '__main__':
    unittest.main()
