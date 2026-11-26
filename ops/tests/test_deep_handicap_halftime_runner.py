import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_halftime_runner import select_group,GROUP_IDS

def index():
    return [{"match_id":i,"competition_stage":{"name":"Group Stage"},"match_date":"2022-11-20"} for i in GROUP_IDS]+[{"match_id":i,"competition_stage":{"name":"Other"},"match_date":"2022-12-03"} for i in range(1,17)]

class GroupIndexTests(unittest.TestCase):
    def test_exact_group(self):
        self.assertEqual(len(select_group(index())),48)
        for bad in (True,999999,GROUP_IDS[1]):
            rows=index();rows[0]["match_id"]=bad
            with self.assertRaises(ValueError):select_group(rows)
    def test_duplicate_non_group_and_missing_group(self):
        rows=index();rows[-1]["match_id"]=rows[-2]["match_id"]
        with self.assertRaises(ValueError):select_group(rows)
        rows=index();rows[0]["competition_stage"]["name"]="Other"
        with self.assertRaises(ValueError):select_group(rows)
