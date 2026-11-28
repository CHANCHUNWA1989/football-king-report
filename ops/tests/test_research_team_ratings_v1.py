import unittest
from datetime import datetime,timedelta,timezone
from ops.research_team_ratings_v1 import Fixture,walk_forward_teams

class TeamRatingsTests(unittest.TestCase):
    def data(self,n=45):
        d=datetime(2024,1,1,tzinfo=timezone.utc)
        return [Fixture(d+timedelta(days=i),"H"+str(i%4),"A"+str(i%3),
                        i%4,(i+1)%3,True,d+timedelta(days=i,hours=2)) for i in range(n)]
    def test_prequential_team_ratings(self):
        r=walk_forward_teams(self.data())
        self.assertEqual(r["n_test"],15)
        self.assertEqual(r["teams_seen"],7)
        self.assertTrue(r["team_specific_model"])
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertEqual(len(r["metrics"]),4)
    def test_unverified_fails(self):
        d=self.data()
        f=d[1]
        d[1]=Fixture(f.kickoff,f.home,f.away,f.home_goals,f.away_goals,False)
        with self.assertRaises(ValueError): walk_forward_teams(d)
    def test_reordering_fails(self):
        d=self.data()
        d[2],d[3]=d[3],d[2]
        with self.assertRaises(ValueError): walk_forward_teams(d)
    def test_same_team_fails(self):
        d=self.data()
        f=d[0]
        d[0]=Fixture(f.kickoff,"H0","H0",1,0,True)
        with self.assertRaises(ValueError): walk_forward_teams(d)
    def test_insufficient_fails(self):
        with self.assertRaises(ValueError): walk_forward_teams(self.data(20))
if __name__=="__main__":unittest.main()
