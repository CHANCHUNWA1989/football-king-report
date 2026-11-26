import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_multi_source import route,openfootball,football_data,baseline,blob


def fixture():
    return json.dumps({"name":"Liga MX 2024/25","matches":[
        {"date":"2024-07-05","team1":"A","team2":"B","score":{"ft":[1,0]}},
        {"date":"2024-07-06","team1":"B","team2":"A"}]}).encode()


CSV=b"Country,League,Date,Home,Away,HG,AG\nMexico,Liga MX,05/07/2024,A,B,1,0\n"


class MultiSourceTests(unittest.TestCase):
    def test_open(self):
        r=route("historical_results",[("openfootball",fixture)])
        self.assertEqual(r["metrics"]["finished_matches"],1)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["verified_forward_sample_credit"],0)

    def test_fallback(self):
        def fail():
            raise OSError("unavailable")
        r=route("historical_results",[("openfootball",fail),("football-data",lambda:CSV)])
        self.assertEqual(r["source"],"football-data")
        self.assertEqual(len(r["attempts"]),1)

    def test_no_live_fallback(self):
        def forbidden():
            self.fail("historical source used for live")
        for purpose in ("live_state","live_xg","live_quotes"):
            self.assertNotIn("source",route(purpose,[("openfootball",forbidden)]))

    def test_wrong_scope(self):
        with self.assertRaises(ValueError):
            football_data(CSV.replace(b"Mexico",b"Brazil"))

    def test_invalid_score(self):
        with self.assertRaises(ValueError):
            football_data(CSV.replace(b"1,0",b"1.1,0"))

    def test_duplicate(self):
        with self.assertRaises(ValueError):
            football_data(CSV+CSV.splitlines()[1]+b"\n")

    def test_duplicate_json(self):
        with self.assertRaises(ValueError):
            openfootball(b'{"name":"Liga MX 2024/25","matches":[],"matches":[]}')

    def test_same_day_not_training(self):
        rows=[("2024-07-01",str(i),"B",1,0) for i in range(51)]
        rows.append(("2024-07-02","A","B",0,1))
        r=baseline(rows)
        self.assertEqual(r["historical_assessment_n"],1)
        self.assertIsNotNone(r["log_loss"])

    def test_git_blob(self):
        self.assertEqual(blob(b""),"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391")

    def test_invalid_sources(self):
        r=route("historical_results",[("openfootball",lambda:b"{}")])
        self.assertNotIn("source",r)
        self.assertFalse(r["positive_ev_verified"])
