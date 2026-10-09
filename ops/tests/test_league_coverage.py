"""Six-league fixture agreement is not independent result verification."""
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from league_coverage import audit,LEAGUES


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.t=datetime(2026,10,9,9,tzinfo=timezone.utc)
        self.ko=(self.t+timedelta(days=1)).isoformat()
        self.report={"checked_utc":self.t.isoformat(),"fixtures":{"matches":[
            {"league":"epl","home":"Manchester City","away":"Arsenal",
             "status":"SCHEDULED","kickoff_utc":self.ko,"score_ft":None}]}}
        self.market={"status":"RESEARCH_ONLY",
                     "as_of_utc":(self.t-timedelta(minutes=15)).isoformat(),
                     "production_recommendations":"DISABLED",
                     "events":[{"league":"epl","home":"Man City","away":"Arsenal FC",
                                "kickoff_utc":self.ko}]}

    def test_alias_with_exact_kickoff_confirms_schedule_only(self):
        x=audit(self.report,self.market)
        self.assertEqual(x["total_confirmed_kickoffs"],1)
        self.assertEqual(x["league_coverage"][0]["curated_alias_matches"],1)
        self.assertFalse(x["results_independently_verified_all_leagues"])
        self.assertEqual(len(x["league_coverage"]),6)

    def test_reschedule_disagreement_flagged_not_guessed(self):
        self.market["events"][0]["kickoff_utc"]=(self.t+timedelta(days=1,hours=2)).isoformat()
        x=audit(self.report,self.market)
        self.assertEqual(x["total_confirmed_kickoffs"],0)
        self.assertEqual(x["total_conflicting_kickoffs"],1)

    def test_multi_market_candidates_ambiguous(self):
        self.market["events"].append(dict(self.market["events"][0]))
        x=audit(self.report,self.market)
        self.assertEqual(x["total_ambiguous_candidates"],1)
        self.assertEqual(x["total_confirmed_kickoffs"],0)

    def test_expired_market_does_not_confirm(self):
        self.market["as_of_utc"]=(self.t-timedelta(hours=30)).isoformat()
        x=audit(self.report,self.market)
        self.assertEqual(x["status"],"HOLD")
        self.assertEqual(x["total_confirmed_kickoffs"],0)

    def test_finished_fixture_not_eligible_as_future(self):
        self.report["fixtures"]["matches"][0]["status"]="FINISHED"
        x=audit(self.report,self.market)
        self.assertEqual(x["total_confirmed_kickoffs"],0)

    def test_real_legacy_combined_fixtures_without_league_are_audited(self):
        # V4.1 combines fixture rows without a per-match league field.
        self.report["fixtures"]["matches"][0].pop("league")
        self.report["fixture_source_records"]=[
            {"league":"epl","window_matches":30},
            {"league":"championship","window_matches":35},
            {"league":"bundesliga","window_matches":28}]
        shadow={"status":"SHADOW_ONLY","predictions":[{
            "league":"epl","home":"Manchester City","away":"Arsenal",
            "kickoff_utc":self.ko,"p_home":.6,"p_draw":.2,"p_away":.2
        }]}
        x=audit(self.report,self.market,shadow)
        self.assertEqual(x["league_coverage"][0]["public_fixtures"],30)
        self.assertEqual(x["league_coverage"][0]["two_source_kickoff_agreements"],1)
        self.assertTrue(x["league_coverage"][0]["precise_kickoff_is_shadow_eligible_subset"])
        self.assertFalse(x["results_independently_verified_all_leagues"])

    def test_six_leagues_have_separate_counts(self):
        x=audit(self.report,self.market)
        self.assertEqual(tuple(row["league"] for row in x["league_coverage"]),LEAGUES)
        self.assertEqual(sum(row["public_fixtures"] for row in x["league_coverage"]),1)
        self.assertTrue(all(row["score_crosschecked_with_market"]==0 for row in x["league_coverage"]))


if __name__=="__main__":
    unittest.main()
