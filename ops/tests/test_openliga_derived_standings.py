"""OpenLigaDB fallback: only community finish-score counts, never official table."""
import sys
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openliga_derived_standings import derive_scores

NOW=datetime(2026,10,9,13,tzinfo=timezone.utc)


def match(i=1,*,ko="2026-09-12T14:30:00Z",home=2,away=1,
          shortcut="bl1",done=True):
    return {"matchID":i,"leagueShortcut":shortcut,
            "matchDateTimeUTC":ko,"matchIsFinished":done,
            "team1":{"teamId":10,"teamName":"Club A"},
            "team2":{"teamId":20,"teamName":"Club B"},
            "matchResults":[{"resultTypeID":1,"pointsTeam1":1,"pointsTeam2":1},
                            {"resultTypeID":2,"pointsTeam1":home,"pointsTeam2":away}]}


class DerivedGermanCoverageTests(unittest.TestCase):
    def test_finished_fulltime_only_and_never_claim_official(self):
        rows=[match(),match(2,ko="2026-09-25T14:30:00Z",done=False)]
        x=derive_scores(rows,shortcut="bl1",captured=NOW)
        self.assertEqual(x["season_finished_games_sampled"],1)
        self.assertEqual(x["derived_clubs_with_points"],2)
        self.assertFalse(x["official_league_table_confirmed"])
        self.assertFalse(x["precise_asof_historical_standings_verified"])

    def test_wrong_competition_and_future_games_ignored(self):
        rows=[match(shortcut="bl2"),match(2,ko="2026-11-01T14:30:00Z")]
        x=derive_scores(rows,shortcut="bl1",captured=NOW)
        self.assertEqual(x["season_finished_games_sampled"],0)

    def test_fulltime_not_halftime(self):
        a=match()
        a["matchResults"]=a["matchResults"][:1]
        self.assertEqual(derive_scores([a],shortcut="bl1",captured=NOW)
                         ["season_finished_games_sampled"],0)

    def test_repeated_match_id_rejected_even_when_score_agrees(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_FINISHED_MATCH_ID"):
            derive_scores([match(),match()],shortcut="bl1",captured=NOW)

    def test_changed_team_id_name_rejected(self):
        other=match(2)
        other["team1"]["teamName"]="Unknown Club"
        with self.assertRaisesRegex(ValueError,"CHANGING_TEAM_IDENTITY"):
            derive_scores([match(),other],shortcut="bl1",captured=NOW)

    def test_unsupported_league_and_oversized_season(self):
        with self.assertRaises(ValueError):
            derive_scores([match()],shortcut="unknown",captured=NOW)
        with self.assertRaises(ValueError):
            derive_scores([match()]*601,shortcut="bl1",captured=NOW)

    def test_malformed_scores_boolean_not_accepted(self):
        r=match()
        r["matchResults"][1]["pointsTeam1"]=True
        self.assertEqual(derive_scores([r],shortcut="bl1",captured=NOW)
                         ["season_finished_games_sampled"],0)


if __name__=="__main__":
    unittest.main()
