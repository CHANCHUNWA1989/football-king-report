import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from live_core_statsbomb_event_replay import replay,audit


def events():
    es=[]
    def add(p,t,kind,team,**kw):
        n=len(es)+1
        es.append(dict(id=str(n),index=n,period=p,timestamp=t,type={"name":kind},
                       team={"id":team},**kw))
    for team in (1,2):
        add(1,"00:00:00.000","Starting XI",team,tactics={"lineup":[{"player":{"id":team*100+i}} for i in range(11)]})
    add(1,"00:20:00.000","Shot",1,shot={"statsbomb_xg":.2})
    add(1,"00:30:00.000","Foul Committed",1,player={"id":101},foul_committed={"card":{"name":"Red Card"}})
    add(1,"00:40:00.000","Shot",2,shot={"statsbomb_xg":.4})
    add(1,"00:45:00.000","Half End",1)
    add(2,"00:20:00.000","Shot",2,shot={"statsbomb_xg":.1})
    add(2,"00:45:00.000","Half End",2)
    add(5,"00:00:00.000","Bad Behaviour",2,player={"id":201},bad_behaviour={"card":{"name":"Second Yellow"}})
    return es


class StatsBombReplayTests(unittest.TestCase):
    def test_exposure(self):
        r=replay(events(),1,2)
        self.assertEqual(r["regulation_cards"],1)
        self.assertEqual(r["ignored_nonregulation_cards"],1)
        self.assertEqual(r["buckets"][0]["elapsed_minutes"],30)
        self.assertEqual(r["buckets"][1]["elapsed_minutes"],60)
        self.assertEqual(r["buckets"][1]["shots"],[0,2])
        self.assertAlmostEqual(r["buckets"][1]["xg"][1],.5)
        self.assertFalse(r["model_calibrated"])
    def test_missing_xg(self):
        e=events();del e[2]["shot"]["statsbomb_xg"]
        with self.assertRaises(KeyError):replay(e,1,2)
    def test_non_roster_red(self):
        e=events();e[3]["player"]["id"]=999
        with self.assertRaises(ValueError):replay(e,1,2)
    def test_duplicate(self):
        e=events();e[4]["id"]=e[3]["id"]
        with self.assertRaises(ValueError):replay(e,1,2)
    def test_regression(self):
        e=events();e[4]["timestamp"]="00:29:00.000"
        with self.assertRaises(ValueError):replay(e,1,2)
    def test_missing_half_end(self):
        e=events();e.pop(7)
        with self.assertRaises(ValueError):replay(e,1,2)
    def test_digest(self):
        raw=json.dumps(events()).encode()
        pin=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
        self.assertEqual(audit(raw,pin,1,2)["regulation_cards"],1)
        self.assertEqual(audit(raw+b" ",pin,1,2)["reason"],"EVENT_REVIEW_REQUIRED")
