import unittest
from live_core_halftime_dynamics import fit,distribution,report,bucket,parse

class HalftimeDynamicsTests(unittest.TestCase):
    def setUp(self):
        self.train=[("2020-10-01","A","B",0,1,2,1),
                    ("2020-10-02","C","D",1,0,1,2),
                    ("2020-10-03","E","F",0,0,0,0)]
    def test_normalized_and_never_retract_goals(self):
        for h,a in ((0,0),(1,0),(0,2),(8,0)):
            for conditional in (False,True):
                d=distribution(fit(self.train),h,a,conditional)
                self.assertAlmostEqual(sum(d.values()),1.)
                self.assertTrue(all(i>=h and j>=a for i,j in d))
    def test_bucket_and_unseen_state_fallback(self):
        self.assertEqual(bucket(5,0),2)
        m=fit(self.train)
        self.assertEqual(distribution(m,4,0,True),distribution(m,4,0,False))
    def test_invalid_scores(self):
        with self.assertRaises(ValueError):fit([("2020-10-01","A","B",2,0,1,0)])
        with self.assertRaises(ValueError):distribution(fit(self.train),True,0,True)
    def test_temporal_overlap_and_pin(self):
        with self.assertRaises(ValueError):report(self.train,self.train)
        with self.assertRaises(ValueError):parse(b"{}","2020-21")
    def test_report_never_promotes(self):
        r=report(self.train,[("2021-10-01","A","B",0,1,2,1)])
        self.assertEqual(r["candidate"]["trailing_n"],1)
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["red_card_or_xg_used"])
