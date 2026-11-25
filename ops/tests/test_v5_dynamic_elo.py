import copy
import unittest
from datetime import date,timedelta
from ops.v5_dynamic_elo import build,parse_archive,probabilities,rates,replay

def fixture():
    rows=[]
    start=date(2025,8,1)
    for i in range(25):
        d=(start+timedelta(days=i)).isoformat()
        rows.extend([{"date":d,"team1":"A","team2":"B","score":{"ft":[3,0]}},
                     {"date":d,"team1":"C","team2":"D","score":[1,1]}])
    return {"matches":rows}

class DynamicEloTest(unittest.TestCase):
    def test_normalized_and_elo_effect(self):
        p=probabilities(2,1)
        self.assertAlmostEqual(sum(p),1)
        self.assertGreater(p[0],p[2])
        rows=parse_archive(fixture())
        day=date(2025,9,1)
        h,a=rates(rows,day,"A","B",{"A":1700,"B":1300},True)
        h0,a0=rates(rows,day,"A","B",{"A":1500,"B":1500},True)
        self.assertGreater(h,h0)
        self.assertLess(a,a0)
    def test_same_day_and_future_outcomes_do_not_change_probabilities(self):
        d=fixture()
        a=replay(d)
        other=copy.deepcopy(d)
        other["matches"][-2]["score"]={"ft":[0,5]}
        other["matches"][-1]["score"]=[5,0]
        b=replay(other)
        self.assertTrue(a)
        self.assertEqual([(x["baseline"],x["candidate"]) for x in a],
                         [(x["baseline"],x["candidate"]) for x in b])
    def test_order_independent(self):
        d=fixture()
        self.assertEqual(replay(d),replay({"matches":list(reversed(d["matches"]))}))
    def test_duplicate_and_invalid_score(self):
        d=fixture()
        d["matches"].append(copy.deepcopy(d["matches"][0]))
        with self.assertRaises(ValueError): build(d)
        d=fixture()
        d["matches"][0]["score"]=[True,0]
        with self.assertRaises(ValueError): build(d)
    def test_nonprior_rejected(self):
        with self.assertRaises(ValueError):
            rates(parse_archive(fixture()),date(2025,8,1),"A","B",{},True)
    def test_hold_small_and_no_production(self):
        d=fixture()
        self.assertEqual(build({"matches":d["matches"][:20]})["status"],"HOLD")
        r=build(d)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["prospective_validation"])
        self.assertFalse(r["cross_league_strength_calibrated"])
        self.assertGreater(r["metrics"]["candidate"]["n"],0)
    def test_explicit_historical_mode_retains_actual_dates(self):
        d=fixture()
        for row in d["matches"]:
            row["date"]="2022"+row["date"][4:]
        with self.assertRaisesRegex(ValueError,"INVALID_DATE"):
            replay(d)
        cases=replay(d,historical=True)
        self.assertTrue(cases)
        self.assertTrue(all(r["date"].startswith("2022-") for r in cases))
        d["matches"][0]["date"]="2020-08-01"
        with self.assertRaisesRegex(ValueError,"INVALID_DATE"):
            replay(d,historical=True)
if __name__=="__main__":
    unittest.main()
