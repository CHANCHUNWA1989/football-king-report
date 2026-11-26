import hashlib
import json
import unittest
from test_live_core_statsbomb_event_replay import events
from live_core_statsbomb_shot_quality import shot_rows,summarize

def encode(es):
    raw=json.dumps(es).encode()
    pin=hashlib.sha1(("blob "+str(len(raw))+"\0").encode()+raw).hexdigest()
    return raw,pin

def valid_events():
    es=events()
    for i,typ,outcome in ((2,"Open Play","Goal"),(4,"Penalty","Saved"),(6,"Open Play","Blocked")):
        es[i]["shot"].update(type={"name":typ},outcome={"name":outcome})
    return es

class ShotQualityTests(unittest.TestCase):
    def test_regulation_only_penalty_split_and_bins(self):
        es=valid_events()
        es[-1].update(type={"name":"Shot"},shot={"statsbomb_xg":.8,"type":{"name":"Penalty"},"outcome":{"name":"Goal"}})
        r=summarize(shot_rows(*encode(es),1,2))
        self.assertEqual(r["all_shots"]["shots"],3)
        self.assertEqual(r["nonpenalty"]["shots"],2)
        self.assertEqual(r["penalty"]["shots"],1)
        self.assertEqual(r["all_shots"]["goals_from_shots"],1)
        self.assertAlmostEqual(r["all_shots"]["brier"],(.8**2+.4**2+.1**2)/3)
        self.assertEqual(sum(x["n"] for x in r["all_shots"]["bins"]),3)
    def test_missing_or_unknown_outcome_not_miss(self):
        for outcome in (None,{"name":"Unknown"}):
            es=valid_events()
            if outcome is None:del es[2]["shot"]["outcome"]
            else:es[2]["shot"]["outcome"]=outcome
            with self.assertRaises((ValueError,KeyError)):shot_rows(*encode(es),1,2)
    def test_empty_groups_are_unknown(self):
        r=summarize([])
        self.assertIsNone(r["all_shots"]["brier"])
        self.assertIsNone(r["penalty"]["ece"])
    def test_digest_and_existing_event_guard(self):
        es=valid_events()
        raw,pin=encode(es)
        with self.assertRaises(ValueError):shot_rows(raw+b" ",pin,1,2)
        es[3]["player"]["id"]=999
        with self.assertRaises(ValueError):shot_rows(*encode(es),1,2)
