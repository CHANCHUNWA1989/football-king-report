import sys
import unittest
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_red_card_roster import roster_status,reconcile
from deep_handicap_red_card_windows import inspect
from test_deep_handicap_red_card_windows import fixture

def case():
    m,e=fixture()
    for team,players in ((10,list(range(100,111))),(20,list(range(200,211)))):
        e.insert(0,{"id":f"xi{team}","period":1,"timestamp":"00:00:00.000",
                    "type":{"name":"Starting XI"},"team":{"id":team},
                    "tactics":{"lineup":[{"player":{"id":p}} for p in players]}})
    return m,e

def run(m,e):
    for i,r in enumerate(e,1):r["index"]=i
    raw=json.dumps(e).encode()
    return roster_status(raw,m,inspect(raw,m))

class RedRosterTests(unittest.TestCase):
    def test_active_and_bench_card(self):
        m,e=case()
        self.assertEqual(run(m,e),"ROSTER_SUPPORTED_CLAIM")
        next(r for r in e if r["id"]=="red")["player"]["id"]=999
        self.assertEqual(run(m,e),"NON_ACTIVE_ROSTER_CARD")
    def test_substitution_and_temporary_exit(self):
        m,e=case()
        e.insert(3,{"id":"sub","period":1,"timestamp":"00:09:00.000","type":{"name":"Substitution"},
                    "team":{"id":10},"player":{"id":100},"substitution":{"replacement":{"id":999}}})
        self.assertEqual(run(m,e),"NON_ACTIVE_ROSTER_CARD")
        next(r for r in e if r["id"]=="red")["player"]["id"]=999
        self.assertEqual(run(m,e),"ROSTER_SUPPORTED_CLAIM")
        m,e=case()
        e.insert(3,{"id":"off","period":1,"timestamp":"00:09:00.000","type":{"name":"Player Off"},
                    "team":{"id":10},"player":{"id":100}})
        self.assertEqual(run(m,e),"NON_ACTIVE_ROSTER_CARD")
    def test_same_clock_and_duplicate_xi_identity(self):
        m,e=case()
        e.insert(3,{"id":"sub","period":1,"timestamp":"00:12:00.000","type":{"name":"Substitution"},
                    "team":{"id":10},"player":{"id":100},"substitution":{"replacement":{"id":999}}})
        self.assertEqual(run(m,e),"ROSTER_AMBIGUOUS")
        m,e=case()
        e[0]["tactics"]["lineup"][0]["player"]["id"]=100
        self.assertEqual(run(m,e),"ROSTER_AMBIGUOUS")
    def test_partition_and_no_card(self):
        m,e=case()
        next(r for r in e if r["id"]=="red")["foul_committed"]["card"]["name"]="Yellow Card"
        self.assertEqual(run(m,e),"NOT_PAIRED_WINDOW")
        self.assertEqual(sum(reconcile(["NOT_PAIRED_WINDOW","ROSTER_AMBIGUOUS"],2).values()),2)
        with self.assertRaises(ValueError):reconcile(["ROSTER_SUPPORTED_CLAIM"],2)
