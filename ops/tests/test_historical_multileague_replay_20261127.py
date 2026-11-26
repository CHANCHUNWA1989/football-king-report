import unittest
from datetime import date,timedelta
from ops.historical_multileague_replay_20261127 import week_bootstrap,MANIFEST
from ops.historical_season_replay_20261127 import replay,replay_pairs

class MultileagueTests(unittest.TestCase):
    def test_bootstrap_reproducibility(self):
        pairs=[(date(2024,1,1)+timedelta(weeks=w,days=d),(-.1,-.2,-.3))
               for w in range(20) for d in range(5)]
        a=week_bootstrap(pairs)
        self.assertEqual(a,week_bootstrap(pairs))
        self.assertEqual(a["weeks"],20)
        self.assertEqual(a["draws"],2000)
        for interval,expected in zip(a["intervals"].values(),(-.1,-.2,-.3)):
            for x in interval: self.assertAlmostEqual(x,expected)
    def test_small(self):
        self.assertIsNone(week_bootstrap([(date(2024,1,1),(0,0,0))]*100)["intervals"])
    def test_pair_api(self):
        tr=[(date(2023,1,1),"A","B",(2,1)),(date(2023,1,2),"B","A",(1,2))]
        te=[(date(2024,1,1),"A","B",(1,0)),(date(2024,1,8),"B","A",(1,1))]
        r,pairs=replay_pairs(tr,te)
        self.assertEqual(r,replay(tr,te))
        self.assertEqual(len(pairs),2)
        for i,m in enumerate(r["delta"]):
            self.assertAlmostEqual(sum(v[1][i] for v in pairs)/2,r["delta"][m])
    def test_manifest(self):
        self.assertEqual(sum(v[1] for v in MANIFEST.values()),992)
        self.assertEqual(len({h for v in MANIFEST.values() for h in v[2:]}),6)

if __name__=="__main__": unittest.main()
