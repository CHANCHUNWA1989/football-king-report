import unittest
from datetime import datetime,timedelta,timezone
from ops.research_walkforward_v1 import Match,walk_forward

class ResearchWalkForwardTests(unittest.TestCase):
    def samples(self,n=40):
        base=datetime(2024,1,1,tzinfo=timezone.utc)
        return [Match(base+timedelta(days=i),i%4,(i+1)%3,True,base+timedelta(days=i,hours=2)) for i in range(n)]
    def test_offline_prequential(self):
        result=walk_forward(self.samples(),warmup=30)
        self.assertEqual(result["n_test"],10)
        self.assertEqual(result["status"],"RESEARCH_ONLY")
        self.assertFalse(result["qualified_for_production"])
        self.assertEqual(len(result["mean_metrics"]),4)
    def test_unverified_rejected(self):
        records=self.samples()
        records[5]=Match(records[5].kickoff_utc,1,0,False)
        with self.assertRaises(ValueError): walk_forward(records)
    def test_future_and_duplicate_rejected(self):
        records=self.samples()
        records[3]=records[2]
        with self.assertRaises(ValueError): walk_forward(records)
    def test_naive_date_rejected(self):
        records=self.samples()
        records[0]=Match(datetime(2024,1,1),1,0,True)
        with self.assertRaises(ValueError): walk_forward(records)
    def test_insufficient_samples(self):
        with self.assertRaises(ValueError): walk_forward(self.samples(20),warmup=30)

if __name__=="__main__":unittest.main()
