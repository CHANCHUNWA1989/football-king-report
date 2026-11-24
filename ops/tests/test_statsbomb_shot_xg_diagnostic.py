import copy
import hashlib
import json
import unittest
from ops.statsbomb_shot_xg_diagnostic import summarize_shots


def shot(eid, team, xg, outcome="Saved", kind="Open Play", period=1):
    return {"id": eid, "type": {"name": "Shot"}, "period": period,
            "team": {"id": team}, "shot": {"statsbomb_xg": xg,
            "type": {"name": kind}, "outcome": {"name": outcome}}}


def packet(events):
    raw = json.dumps(events).encode()
    rec = {"match_id": 123, "home_team_id": 1, "away_team_id": 2,
           "events": {"bytes": len(raw), "records": len(events),
                      "sha256": hashlib.sha256(raw).hexdigest()}}
    return raw, rec


class ShotXGDiagnosticTests(unittest.TestCase):
    def test_regulation_penalty_and_defense(self):
        raw, rec = packet([shot("a", 1, .2), shot("b", 1, .8, "Goal", "Penalty"),
                           shot("c", 2, .4, "Goal"), shot("d", 2, .9, "Goal", period=5)])
        r = summarize_shots(raw, rec)
        h, a = r["teams"]["1"], r["teams"]["2"]
        self.assertEqual(r["excluded_extra_time_or_shootout_shots"], 1)
        self.assertEqual(h["attack"]["all"]["shots"], 2)
        self.assertAlmostEqual(h["attack"]["all"]["xg"], 1)
        self.assertEqual(h["attack"]["all"]["shot_goals"], 1)
        self.assertAlmostEqual(h["attack"]["non_penalty"]["xg"], .2)
        self.assertEqual(h["attack"]["non_penalty"]["shot_goals"], 0)
        self.assertEqual(h["defense"], a["attack"])
        self.assertEqual(a["defense"], h["attack"])
        self.assertAlmostEqual(h["attack"]["all"]["shot_brier"], .04)

    def test_zero_shots_and_own_goal(self):
        raw, rec = packet([{"id": "a", "type": {"name": "Own Goal For"}}])
        r = summarize_shots(raw, rec)
        a = r["teams"]["1"]["attack"]["all"]
        self.assertEqual(a["xg"], 0)
        self.assertEqual(a["shot_goals"], 0)
        self.assertIsNone(a["xg_per_shot"])
        self.assertIsNone(a["shot_brier"])

    def test_invalid_xg(self):
        for x in (None, True, -0.1, 1.1, "0.4", float("nan"), float("inf")):
            with self.subTest(x=x), self.assertRaises(ValueError):
                summarize_shots(*packet([shot("a", 1, x)]))

    def test_wrong_team_and_duplicate(self):
        for events in ([shot("a", 3, .2)], [shot("a", 1, .2), shot("a", 2, .2)],
                       [shot("a", 1, .2, period=True)]):
            with self.subTest(events=events), self.assertRaises(ValueError):
                summarize_shots(*packet(events))

    def test_byte_and_record_binding(self):
        raw, rec = packet([shot("a", 1, .2)])
        with self.assertRaisesRegex(ValueError, "EVENT_BYTES_MISMATCH"):
            summarize_shots(raw.replace(b"0.2", b"0.3"), rec)
        bad = copy.deepcopy(rec)
        bad["events"]["records"] += 1
        with self.assertRaisesRegex(ValueError, "EVENT_COUNT_MISMATCH"):
            summarize_shots(raw, bad)

    def test_duplicate_json_key(self):
        raw = b'[{"id":"a","id":"b","type":{"name":"Pass"}}]'
        _, rec = packet([shot("a", 1, .2)])
        rec["events"].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
            summarize_shots(raw, rec)


if __name__ == "__main__":
    unittest.main()
