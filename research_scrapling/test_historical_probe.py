"""Offline contract tests. Never use network, secrets or production paths."""
import json
import unittest
from unittest.mock import patch
import historical_probe as p

def liga():
    return [{"matchID":58577,"matchDateTimeUTC":"2020-09-18T18:30:00Z",
             "team1":{"teamId":40},"team2":{"teamId":9},"matchIsFinished":True,
             "matchResults":[{"resultTypeID":1,"pointsTeam1":3,"pointsTeam2":0},
                             {"resultTypeID":2,"pointsTeam1":8,"pointsTeam2":0}]}]

def foot():
    return {"matches":[{"date":"2020-09-18","team1":"Bayern München",
                        "team2":"Schalke 04","score":{"ft":[8,0]}}]}

def ecb(value="1.18",currency="USD",date="2020-09-18"):
    return ("TIME_PERIOD,CURRENCY,CURRENCY_DENOM,OBS_VALUE\n"
            +date+","+currency+",EUR,"+value+"\n").encode()

class ContractTests(unittest.TestCase):
    def test_final_not_halftime(self):
        self.assertEqual(p.openliga_score(liga()),(8,0))
    def test_football_match(self):
        self.assertEqual(p.score_pair(p.openliga_score(liga()),p.openfoot_score(foot())),"HISTORICAL_MATCH")
    def test_conflict(self):
        self.assertEqual(p.score_pair([8,0],[7,0]),"HOLD_CONFLICT")
    def test_bad_scores(self):
        for x in ([True,0],[-1,0],[1.5,0],[1],["1",0]):
            with self.subTest(x=x),self.assertRaises(ValueError):
                p.score_pair(x,[1,0])
    def test_not_finished(self):
        d=liga();d[0]["matchIsFinished"]=False
        with self.assertRaises(ValueError):p.openliga_score(d)
    def test_duplicate_fixture(self):
        with self.assertRaises(ValueError):p.openliga_score(liga()+liga())
    def test_duplicate_final(self):
        d=liga();d[0]["matchResults"].append(d[0]["matchResults"][-1])
        with self.assertRaises(ValueError):p.openliga_score(d)
    def test_wrong_date(self):
        d=foot();d["matches"][0]["date"]="2020-09-19"
        with self.assertRaises(ValueError):p.openfoot_score(d)
    def test_duplicate_openfootball(self):
        d=foot();d["matches"]*=2
        with self.assertRaises(ValueError):p.openfoot_score(d)
    def test_ecb(self):
        self.assertEqual(p.ecb_observation(ecb()),"1.18")
    def test_ecb_wrong_series(self):
        with self.assertRaises(ValueError):p.ecb_observation(ecb(currency="JPY"))
    def test_ecb_nonfinite(self):
        for v in ("NaN","Infinity","0","-1"):
            with self.subTest(v=v),self.assertRaises(ValueError):p.ecb_observation(ecb(v))
    def test_ecb_duplicate(self):
        with self.assertRaises(ValueError):p.ecb_observation(ecb()+b"2020-09-18,USD,EUR,1.18\n")
    def test_disallowed_endpoint(self):
        with self.assertRaises(ValueError):p.acquire("https://example.com/")
    def test_network_failure_stays_hold(self):
        with patch.object(p,"acquire",side_effect=TimeoutError):
            r=p.run("football")
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["error_type"],"TimeoutError")
    def test_historical_never_authorizes(self):
        with patch.object(p,"acquire",side_effect=[(json.dumps(liga()).encode(),{}),(json.dumps(foot()).encode(),{})]):
            r=p.run("football")
        self.assertEqual(r["historical_comparison"],"HISTORICAL_MATCH")
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertFalse(r["independent_upstream_certified"])
    def test_single_publisher_never_authorizes(self):
        with patch.object(p,"acquire",return_value=(ecb(),{})):
            r=p.run("quant")
        self.assertEqual(r["historical_comparison"],"HOLD_SINGLE_PUBLISHER")
        self.assertEqual(r["live_trading"],"DISABLED")
        self.assertEqual(r["status"],"HOLD")

if __name__=="__main__":
    unittest.main(verbosity=2)
