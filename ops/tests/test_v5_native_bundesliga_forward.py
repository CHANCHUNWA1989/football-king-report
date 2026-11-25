import copy
import unittest
from datetime import datetime,timezone
from ops.v5_native_bundesliga_forward import normalize,decode,feature,WEIGHTS
NOW=datetime(2026,11,25,14,tzinfo=timezone.utc)
def fixture(mid=1,done=False):
    return {"leagueShortcut":"bl1","leagueSeason":2026,"leagueId":1,"matchID":mid,
        "team1":{"teamId":11,"teamName":"A"},"team2":{"teamId":22,"teamName":"B"},
        "matchDateTimeUTC":"2026-11-28T14:30:00Z","matchIsFinished":done,"matchResults":[]}
class NativeTests(unittest.TestCase):
    def test_fixture_uses_native_ids(self):
        r=normalize([fixture()],2026,NOW)
        self.assertEqual(r["fixtures"][0]["h"],"11")
        self.assertEqual(r["history"]["matches"],[])
    def test_wrong_season_and_duplicates(self):
        with self.assertRaises(ValueError):normalize([fixture()],2025,NOW)
        with self.assertRaises(ValueError):normalize([fixture(),fixture(2)],2026,NOW)
    def test_future_final_and_live_results(self):
        with self.assertRaises(ValueError):normalize([fixture(done=True)],2026,NOW)
        f=fixture();f["matchResults"]=[{"resultTypeID":1}]
        self.assertFalse(normalize([f],2026,NOW)["fixtures"])
    def test_finished_and_same_day(self):
        f=fixture(done=True);f["matchDateTimeUTC"]="2026-11-24T14:30:00Z"
        f["matchResults"]=[{"resultTypeID":2,"pointsTeam1":2,"pointsTeam2":1}]
        self.assertEqual(normalize([f],2026,NOW)["history"]["matches"][0]["score"],[2,1])
        f["matchDateTimeUTC"]="2026-11-25T10:00:00Z"
        self.assertEqual(normalize([f],2026,NOW)["history"]["matches"],[])
    def test_duplicate_json_and_weights(self):
        with self.assertRaises(ValueError):decode(b'{"x":1,"x":2}')
        self.assertAlmostEqual(sum(WEIGHTS.values()),1)
    def test_incomplete_previous(self):
        with self.assertRaises(ValueError):normalize([fixture()],2026,NOW,previous=True)
