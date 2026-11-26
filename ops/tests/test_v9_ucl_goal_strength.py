import unittest
from datetime import date,timedelta
from ops.v9_ucl_goal_strength import replay,rates,mix

def history():
    d=date(2024,8,1)
    rows=[(d+timedelta(days=i),"A","B","ENG","ESP",2,1,"2024-25") for i in range(100)]
    rows.append((d+timedelta(days=99),"C","D","ENG","ESP",1,1,"2024-25"))
    return rows

class UCLGoalStrengthTests(unittest.TestCase):
    def test_same_day_isolation_and_order(self):
        rows=history();a=replay(rows)
        rows[-1]=(*rows[-1][:5],9,0,rows[-1][-1])
        b=replay(rows)
        self.assertEqual([r["goal_strength"] for r in a],[r["goal_strength"] for r in b])
        self.assertEqual(b,replay(rows[::-1]))
    def test_previous_goal_update(self):
        rows=history();a=replay(rows)
        rows[96]=(*rows[96][:5],7,0,rows[96][-1])
        b=replay(rows)
        self.assertEqual(a[0]["goal_strength"],b[0]["goal_strength"])
        self.assertNotEqual(a[1]["goal_strength"],b[1]["goal_strength"])
        for r in b:self.assertAlmostEqual(sum(r["goal_strength"]),1)
    def test_country_effect_and_mix(self):
        d=date(2024,9,1)
        base=rates({},"A","B","ENG","ESP",d)
        p=rates({("country","attack","ENG"):(.2,d)},"A","B","ENG","ESP",d)
        self.assertGreater(p[0],base[0])
        self.assertEqual(p[1],base[1])
        self.assertEqual(mix([.5,.3,.2],[.3,.3,.4],0.),[.5,.3,.2])
    def test_duplicate_rejected(self):
        rows=history()
        with self.assertRaisesRegex(ValueError,"UCL_STRENGTH_CASE"):replay(rows+[rows[0]])
