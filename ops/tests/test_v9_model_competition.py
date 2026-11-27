import unittest
from datetime import date,timedelta
from ops.v9_model_competition import decision,replay,NAMES

def row(i,y=0):
    return {"league":"en.1","season":"2025-26","date":(date(2025,8,1)+timedelta(days=i//2)).isoformat(),
            "home":str(i),"away":"B","y":y,"stack":[.5,.3,.2],"v8":[.8,.1,.1],
            "ensemble":[.5,.3,.2],"candidate":[.5,.3,.2]}
class ModelCompetitionTests(unittest.TestCase):
    def test_admit_quarantine_reentry(self):
        a=[row(i) for i in range(48)]
        w,state,_=decision(a,{})
        self.assertTrue(state["v8"]);self.assertEqual(w["stack"],.5)
        self.assertAlmostEqual(sum(w.values()),1)
        b=a+[row(i,2) for i in range(48,72)]
        w,state,_=decision(b,state)
        self.assertFalse(state["v8"]);self.assertEqual(w["stack"],1)
        w,state,_=decision(b+[row(i) for i in range(72,168)],state)
        self.assertTrue(state["v8"])
    def test_same_day_outcomes_do_not_change_predictions(self):
        rows=[row(i) for i in range(60)]
        a=replay(rows);rows[-2]["y"]=2;rows[-1]["y"]=1
        b=replay(rows)
        self.assertEqual([r["competition"] for r in a],[r["competition"] for r in b])
        self.assertEqual(b,replay(rows[::-1]))
    def test_insufficient_history_and_duplicate(self):
        a=replay([row(i) for i in range(10)])
        self.assertTrue(all(r["weights"]["stack"]==1 for r in a))
        with self.assertRaisesRegex(ValueError,"COMPETITION_CASE"):replay([row(0),row(0)])
    def test_league_isolation(self):
        rows=[row(i) for i in range(60)]
        other=dict(row(100),league="de.1")
        r=[r for r in replay(rows+[other]) if r["league"]=="de.1"][0]
        self.assertEqual(r["prior_n"],0);self.assertEqual(r["weights"]["stack"],1)
