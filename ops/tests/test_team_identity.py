"""Audited aliases never relax the pre-match time and league constraints."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from team_identity import team_id, same_team, alias_index
from market_pair import pair


class IdentityTests(unittest.TestCase):
    def test_all_aliases_nonconflicting(self):
        x=alias_index()
        self.assertEqual(set(x),{"epl","championship","bundesliga","laliga","seriea","ligue1"})

    def test_common_club_names(self):
        for league, left, right in (
            ("epl","Manchester City","Man City"),
            ("bundesliga","Bayern München","Bayern Munich"),
            ("seriea","Internazionale","Inter Milan"),
            ("laliga","Atlético de Madrid","Atletico Madrid"),
            ("ligue1","Paris Saint-Germain","PSG"),
            ("championship","West Bromwich Albion","West Brom"),
        ):
            with self.subTest(league=league):
                self.assertTrue(same_team(league,left,right))

    def test_championship_promoted_relegated_explicit_aliases(self):
        for left, right in (
            ("Wolverhampton Wanderers", "Wolverhampton Wanderers FC"),
            ("West Ham United", "West Ham United FC"),
            ("Southampton", "Southampton FC"),
            ("Burnley", "Burnley FC"),
            ("Watford", "Watford FC"),
            ("Birmingham City", "Birmingham City FC"),
            ("Portsmouth", "Portsmouth FC"),
        ):
            with self.subTest(left=left):
                self.assertTrue(same_team("championship", left, right))
        self.assertFalse(same_team("championship", "Birmingham City", "Cardiff City"))

    def test_league_scoped_alias_not_global(self):
        self.assertFalse(same_team("championship","Manchester City","Man City"))
        self.assertFalse(same_team("epl","Bayern München","Bayern Munich"))

    def test_distinct_squads_stay_distinct(self):
        for league, left,right in (("epl","Everton","Everton Women"),
                                  ("seriea","Inter Milan","AC Milan"),
                                  ("laliga","Real Madrid","Real Sociedad")):
            self.assertFalse(same_team(league,left,right))

    def test_unknown_not_guessed(self):
        self.assertFalse(same_team("epl","Team A","Team B"))
        self.assertEqual(team_id("epl","Acme FC"),"acmefc")

    def test_explicit_alias_increases_safe_pairing(self):
        now=datetime(2026,10,9,10,tzinfo=timezone.utc)
        ko=(now+timedelta(days=2)).isoformat()
        forecast={"league":"epl","home":"Manchester City","away":"Arsenal",
                  "kickoff_utc":ko,"prediction_utc":now.isoformat(),
                  "p_home":.5,"p_draw":.3,"p_away":.2,
                  "production_recommendations":"DISABLED"}
        shadow={"status":"SHADOW_ONLY","as_of_utc":now.isoformat(),
                "predictions":[forecast],"production_recommendations":"DISABLED"}
        market={"status":"RESEARCH_ONLY",
                "as_of_utc":(now-timedelta(minutes=10)).isoformat(),
                "events":[{"league":"epl","home":"Man City","away":"Arsenal FC",
                           "source_event_id":"event-1","kickoff_utc":ko,
                           "market_last_update_utc":(now-timedelta(minutes=12)).isoformat(),
                           "p_home":.55,"p_draw":.25,"p_away":.20}],
                "production_recommendations":"DISABLED"}
        accepted=pair(shadow,market)
        self.assertEqual(accepted["matched_count"],1)
        self.assertEqual(accepted["verified_alias_pairs"],1)
        market["events"][0]["kickoff_utc"]=(now+timedelta(days=2,hours=3)).isoformat()
        self.assertEqual(pair(shadow,market)["matched_count"],0)


if __name__=="__main__":
    unittest.main()
