"""Synthetic-only tests; no third-party event data is redistributed."""
import hashlib
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_historical_inputs import inspect, rest_interval

NOW="2026-11-27T08:00:00Z"


def events():
    def shot(i,period,team,player,xg):
        return {"id":f"event{i}","index":i,"period":period,"type":{"name":"Shot"},
                "team":{"id":team},"player":{"id":player},"shot":{"statsbomb_xg":xg}}
    return [shot(1,1,10,100,.2),{"id":"end1","index":2,"period":1,"type":{"name":"Half End"}},
            shot(3,2,20,200,.3),shot(4,2,10,100,.4),
            {"id":"end2","index":5,"period":2,"type":{"name":"Half End"}},
            shot(6,3,10,100,.9),shot(7,5,20,200,.8)]


def run(rows=None,**changes):
    raw=json.dumps(events() if rows is None else rows).encode()
    m={"source":"statsbomb_open_data","match_id":1,"home_team_id":10,"away_team_id":20,
       "event_path":"data/events/1.json","status":"FINISHED_REGULATION_CLAIM",
       "kickoff_utc":"2026-11-25T12:00:00Z","regulation_end_utc":"2026-11-25T14:00:00Z",
       "captured_utc":"2026-11-26T08:00:00Z","events_sha256":hashlib.sha256(raw).hexdigest()}
    m.update(changes)
    return inspect(raw,m,as_of_utc=NOW)


class HistoricalInputTests(unittest.TestCase):
    def test_shot_sums_and_extra_time_exclusion(self):
        r=run()
        p=r["private_features"]
        self.assertEqual(p["home_shots"],2)
        self.assertEqual(p["away_shots"],1)
        self.assertAlmostEqual(p["home_shot_xg"],.6)
        self.assertAlmostEqual(p["home_shot_xga"],.3)
        self.assertAlmostEqual(p["players"][0]["shot_xg"],.6)
        self.assertFalse(r["model_inputs_enabled"])
        self.assertFalse(r["source_authenticated"])
        self.assertEqual(r["true_forward_sample_count"],0)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_malformed_shots_and_incomplete_sequences(self):
        changes=[lambda x:x[0]["shot"].pop("statsbomb_xg"),
                 lambda x:x[0]["shot"].update(statsbomb_xg=True),
                 lambda x:x[0]["shot"].update(statsbomb_xg=1.1),
                 lambda x:x[0]["team"].update(id=999),
                 lambda x:x[2]["player"].update(id=100),
                 lambda x:x[2].update(id="event1"),
                 lambda x:x[2].update(index=1),
                 lambda x:x[0].update(match_id=2),
                 lambda x:x[4]["type"].update(name="Pass"),
                 lambda x:x.pop(2)]
        for change in changes:
            e=events()
            change(e)
            self.assertIsNone(run(e)["private_features"])

    def test_metadata_time_digest_and_binding(self):
        for changes in ({"event_path":"data/events/2.json"},{"events_sha256":"0"*64},
                        {"captured_utc":"2026-11-28T08:00:00Z"},
                        {"captured_utc":"2026-11-25T13:00:00Z"},
                        {"status":"LIVE"},{"home_team_id":True}):
            self.assertIsNone(run(**changes)["private_features"])

    def test_rest_is_not_fatigue(self):
        r=rest_interval("2026-11-25T14:00:00Z","2026-11-28T14:00:00Z",
                        observed_utc="2026-11-26T08:00:00Z",as_of_utc=NOW)
        self.assertEqual(r["rest_hours"],72)
        self.assertFalse(r["fatigue_effect_calibrated"])
        self.assertIsNone(rest_interval("2026-11-25T14:00:00Z","2026-11-26T14:00:00Z",
                        observed_utc="2026-11-26T08:00:00Z",as_of_utc=NOW)["rest_hours"])
