import unittest
from datetime import date,timedelta
from ops.v8_ucl_strength import rates,replay,parse
import json
class UCLTests(unittest.TestCase):
    def test_neutral(self):
        b,c=rates([],date(2024,9,1),"a","b","ENG","GER")
        self.assertAlmostEqual(b[0],c[0]);self.assertAlmostEqual(b[1],c[1])
    def test_future(self):
        d=date(2024,9,1)
        with self.assertRaisesRegex(ValueError,"FUTURE"):rates([(d,"a","b","ENG","GER",2,0,"2024-25")],d,"a","b","ENG","GER")
    def test_same_day_no_leakage(self):
        d=date(2012,9,1)
        rows=[(d+timedelta(days=i),f"a{i}","b","ENG","GER",1,0,"2012-13") for i in range(96)]
        r=(d+timedelta(days=97),"a","b","ENG","GER",1,1,"2012-13")
        s=(r[0],"c","b","ENG","GER",0,0,"2012-13")
        a=replay(rows+[r,s]);b=replay(rows+[(*r[:5],9,0,r[-1]),s])
        self.assertEqual(a[-1]["candidate"],b[-1]["candidate"])
    def test_duplicate(self):
        r=(date(2024,9,1),"a","b","ENG","GER",1,1,"2024-25")
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):replay([r,r])
    def test_invalid_score(self):
        r={"round":"League, Matchday 1","date":"2024-09-17","team1":"A (ENG)","team2":"B (GER)","score":{"ft":[2,None]}}
        with self.assertRaisesRegex(ValueError,"REGULATION"):parse(json.dumps({"matches":[r]}).encode(),"2024-25")
