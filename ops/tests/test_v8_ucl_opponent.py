import unittest
from datetime import date,timedelta
from ops.v8_ucl_opponent import update,rating,difference,opponent_rates,replay,decayed
D=date(2024,9,17)
class OpponentTests(unittest.TestCase):
    def test_strength(self):
        c,n={},{}
        update(c,n,[(D,"a","b","ENG","GER",2,0,"2024-25")],D)
        self.assertGreater(difference(c,n,"a","b","ENG","GER",D),0)
        self.assertAlmostEqual(rating(c,"a",D+timedelta(days=365)),rating(c,"a",D)/2)
    def test_future_rating(self):
        with self.assertRaisesRegex(ValueError,"FUTURE"):decayed((10,D),D-timedelta(days=1))
    def test_rate_direction(self):
        h,a=opponent_rates((1.5,1.2),100)
        self.assertGreater(h,1.5);self.assertLess(a,1.2)
        self.assertEqual(opponent_rates((1.5,1.2),0),(1.5,1.2))
    def test_same_day_order(self):
        rows=[(D,"a","b","ENG","GER",2,0,"2024-25"),(D,"c","d","ENG","GER",0,1,"2024-25")]
        c,n,x,y={},{},{},{}
        update(c,n,rows,D);update(x,y,list(reversed(rows)),D)
        self.assertEqual(c,x);self.assertEqual(n,y)
    def test_same_day_no_leakage(self):
        rows=[(D-timedelta(days=100-i),"a","b","ENG","GER",1,0,"2024-25") for i in range(96)]
        a=(D,"a","b","ENG","GER",1,1,"2024-25")
        b=(D,"c","d","ENG","GER",0,1,"2024-25")
        self.assertEqual(replay(rows+[a,b])[-1]["hybrid"],replay(rows+[(D,"a","b","ENG","GER",9,0,"2024-25"),b])[-1]["hybrid"])
