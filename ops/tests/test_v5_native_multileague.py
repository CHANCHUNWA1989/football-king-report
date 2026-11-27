import unittest
from datetime import datetime, timezone, timedelta
from ops.v5_native_bundesliga_forward import normalize, scope
NOW=datetime(2026,11,25,14,tzinfo=timezone.utc)

def season(shortcut,teams):
    rows=[]
    for h in range(1,teams+1):
        for a in range(1,teams+1):
            if h==a:continue
            i=len(rows)+1
            rows.append({"leagueShortcut":shortcut,"leagueSeason":2025,"leagueId":1,
                "matchID":i,"team1":{"teamId":h,"teamName":str(h)},
                "team2":{"teamId":a,"teamName":str(a)},
                "matchDateTimeUTC":(datetime(2025,8,1,tzinfo=timezone.utc)+timedelta(hours=i)).isoformat(),
                "matchIsFinished":True,"matchResults":[{"resultTypeID":2,"pointsTeam1":1,"pointsTeam2":0}]})
    return rows

class MultiLeagueTests(unittest.TestCase):
    def test_full_season_bl2(self):
        x=normalize(season("bl2",18),2025,NOW,previous=True,shortcut="bl2")
        self.assertEqual(len(x["history"]["matches"]),306)
    def test_full_season_bl3(self):
        x=normalize(season("bl3",20),2025,NOW,previous=True,shortcut="bl3")
        self.assertEqual(len(x["history"]["matches"]),380)
    def test_no_cross_league_mixing(self):
        with self.assertRaises(ValueError):normalize(season("bl2",18),2025,NOW,previous=True,shortcut="bl3")
    def test_incomplete_previous_season(self):
        with self.assertRaises(ValueError):normalize(season("bl3",20)[:-1],2025,NOW,previous=True,shortcut="bl3")
    def test_unsupported_league(self):
        with self.assertRaises(ValueError):scope("ucl")
    def test_bl1_default_preserved(self):
        x=normalize(season("bl1",18),2025,NOW,previous=True)
        self.assertEqual(len(x["history"]["matches"]),306)
