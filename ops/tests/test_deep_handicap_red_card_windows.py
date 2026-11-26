import sys
import unittest
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_red_card_windows import inspect,millis
from test_deep_handicap_halftime_study import example

def fixture():
    m,e=example()
    # Put all first-half shots at 05 and 15 minutes; first half end 45.
    for r,t in zip(e,("00:05:00.000","00:15:00.000","00:45:00.000","00:10:00.000","00:25:00.000","00:45:00.000")):
        r["timestamp"]=t
    # Single claimed dismissal at 12 minutes; both goal shots are within window.
    e.insert(1,{"id":"red","period":1,"type":{"name":"Foul Committed"},"team":{"id":10},
                "player":{"id":100},"foul_committed":{"card":{"name":"Red Card"}},"timestamp":"00:12:00.000"})
    for i,r in enumerate(e,1):r["index"]=i
    return m,e

class RedCardWindowsTests(unittest.TestCase):
    def test_pair_and_private_guard(self):
        m,e=fixture();r=inspect(json.dumps(e).encode(),m)
        self.assertEqual(r["reason"],"PAIRED_CLOCK_WINDOWS_PRIVATE_ONLY")
        self.assertAlmostEqual(r["private_windows"]["dismissal_team"]["before"]["shot_xg"],.4)
        self.assertAlmostEqual(r["private_windows"]["dismissal_team"]["after"]["shot_xg"],.3)
        self.assertFalse(r["on_field_dismissal_verified"])
        self.assertEqual(r["true_forward_sample_count"],0)
    def test_second_yellow_and_short_window(self):
        m,e=fixture()
        e[1]["foul_committed"]["card"]["name"]="Second Yellow"
        self.assertEqual(inspect(json.dumps(e).encode(),m)["reason"],"PAIRED_CLOCK_WINDOWS_PRIVATE_ONLY")
        e[1]["timestamp"]="00:04:00.000"
        self.assertIsNone(inspect(json.dumps(e).encode(),m)["private_windows"])
    def test_no_card_and_tie(self):
        m,e=fixture()
        e[1]["foul_committed"]["card"]["name"]="Yellow Card"
        self.assertEqual(inspect(json.dumps(e).encode(),m)["reason"],"NO_DISMISSAL_EVENT")
        e[1]["foul_committed"]["card"]["name"]="Red Card"
        e[1]["timestamp"]=e[0]["timestamp"]="00:12:00.000"
        self.assertEqual(inspect(json.dumps(e).encode(),m)["reason"],"SIMULTANEOUS_SHOT_AMBIGUOUS")
    def test_wrong_type_and_clock(self):
        m,e=fixture();e[1]["type"]["name"]="Pass"
        with self.assertRaises(ValueError):inspect(json.dumps(e).encode(),m)
        with self.assertRaises(ValueError):millis("00:61:00.000")
