import unittest
from hashlib import sha1
from json import dumps
from datetime import date
from ops.historical_season_replay_20261127 import load_season,replay,_prob

def encode(matches):
    raw=dumps({"matches":matches}).encode()
    return raw,sha1(f"blob {len(raw)}\0".encode()+raw).hexdigest()

def fixture(day,h,a,f):
    return {"date":day,"team1":h,"team2":a,"score":{"ft":f}}

class SeasonReplayTests(unittest.TestCase):
    def test_data_and_fallback(self):
        train=load_season(*encode([fixture("2023-01-01","A","B",[2,1]),
                                   fixture("2023-01-02","B","A",[1,1])]))
        test=load_season(*encode([fixture("2024-01-01","C","D",[1,0]),
                                  fixture("2024-01-02","A","B",[1,1])]))
        r=replay(train,test)
        self.assertEqual(r["train"],2)
        self.assertEqual(r["test"],2)
        self.assertEqual(r["unknown_team_fixtures"],1)
        self.assertFalse(r["prospective_verified"])
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["deployment"],"HOLD")
        self.assertEqual(r["recommendations"],"DISABLED")
    def test_no_overlap(self):
        r=[(date(2024,1,1),"A","B",(1,1))]
        with self.assertRaises(ValueError): replay(r,r)
    def test_load_failure(self):
        f=fixture("2023-01-01","A","B",[1,0])
        raw,blob=encode([f])
        with self.assertRaises(ValueError): load_season(raw,"bad")
        for fs in ([f,f],[fixture("2023-01-01","A","B",[True,0])],
                   [fixture("2023-01-01","A","B",[])],[]):
            with self.subTest(fs=fs),self.assertRaises(ValueError):
                load_season(*encode(fs))
    def test_probability(self):
        for a in (0,.5,1,3):
            for b in (0,.5,1,3):
                p=_prob((a,b)); q=_prob((b,a))
                self.assertAlmostEqual(sum(p),1)
                for x,y in zip(p,q[::-1]): self.assertAlmostEqual(x,y)

if __name__=="__main__": unittest.main()
