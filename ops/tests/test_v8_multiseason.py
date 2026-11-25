import unittest,json
from datetime import date
from ops.v8_multiseason import parse,rolling_rates,git_blob,replay
class V8HistoryTests(unittest.TestCase):
    def row(self):
        return {"date":"2025-08-01","team1":"H","team2":"A","score":{"ft":[2,1]}}
    def test_missing_not_result(self):
        r=self.row();x={**r,"team1":"C","score":{}}
        rows,missing,total=parse(json.dumps({"matches":[r,x]}).encode(),"2025-26")
        self.assertEqual((len(rows),missing,total),(1,1,2))
    def test_duplicate(self):
        r=self.row()
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):parse(json.dumps({"matches":[r,r]}).encode(),"2025-26")
    def test_outside(self):
        r=self.row();r["date"]="2024-08-01"
        with self.assertRaisesRegex(ValueError,"OUTSIDE"):parse(json.dumps({"matches":[r]}).encode(),"2025-26")
    def test_neutral_promoted(self):
        self.assertEqual(rolling_rates((1.5,1.),{},"H","A",1.5,1.),(1.5,1.))
    def test_git_blob(self):
        self.assertEqual(git_blob(b""),"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")
    def test_prior_day_and_new_team(self):
        teams=[str(i) for i in range(12)]
        tr=[(date(2025,4,1),h,a,1,1) for h in teams for a in teams if h!=a]
        day=date(2025,8,1)
        a=replay(tr,[(day,"0","new",1,0),(day,"new","1",0,2)],"de.1","2025-26")
        b=replay(tr,[(day,"0","new",5,0),(day,"new","1",0,2)],"de.1","2025-26")
        self.assertEqual(a[1]["candidate"],b[1]["candidate"])
        self.assertFalse(a[0]["known_prior_team_pair"])
