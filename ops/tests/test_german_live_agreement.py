"""German community matchdays only gain confidence from valid independent timestamps."""
import copy,sys,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from german_live_agreement import crosscheck
from live_germany import collect
from live_germany_guard import verify

NOW=datetime.now(timezone.utc)
KO=(NOW+timedelta(hours=3)).isoformat()


def german():
    def provider(url):
        if url.endswith("/bl1"):
            return [{
                "leagueShortcut":"bl1","matchID":177,"matchDateTimeUTC":KO,
                "team1":{"teamName":"Borussia Dortmund"},
                "team2":{"teamName":"SV Werder Bremen"},
                "matchIsFinished":False,"matchResults":[]
            }]
        return []
    return collect(now=NOW,getter=provider)


def secondary():
    return {
        "schema":"football-king-extra-source-audit-v1",
        "started_utc":NOW.isoformat(),
        "collected_utc":NOW.isoformat(),
        "status":"RESEARCH_ONLY","source_tier":"FREE_ONLY",
        "providers":[
            {"provider":key,"configured":key=="thesportsdb",
             "status":"PARTIAL_COVERAGE" if key=="thesportsdb" else "NOT_CONFIGURED",
             "calls_attempted":1 if key=="thesportsdb" else 0,
             "counts_by_league":{l:(1 if l=="bundesliga" and key=="thesportsdb" else 0)
                                  for l in ("epl","championship","bundesliga","laliga","seriea","ligue1")},
             "sampled_fixture_count":1 if key=="thesportsdb" else 0,
             "league_result_verification_complete":False,
             "can_replace_1x2_market":False,
             "original_bookmaker_odds_redistributed":False,
             "production_recommendations":"DISABLED"} for key in
            ("thesportsdb","api_football","football_data_org","sportmonks")],
        "sampled_fixtures":[{
            "league":"bundesliga","home":"Borussia Dortmund","away":"Werder Bremen",
            "kickoff_utc":KO,"provider_event_id":"328",
            "status":"SCHEDULED","score_ft":None,"provider":"thesportsdb"}],
        "coverage_is_complete":False,
        "six_league_independent_results_verified":False,
        "odds_fallback_confirmed":False,
        "original_api_payload_redistributed":False,
        "production_recommendations":"DISABLED",
    }


class CrosscheckTests(unittest.TestCase):
    def test_alias_and_utc_schedule_agreement(self):
        out=crosscheck(german(),secondary(),now=NOW)
        self.assertTrue(out["schedule_crosscheck_completed"])
        self.assertEqual(out["two_source_kickoff_agreements"],1)
        self.assertEqual(out["unverified_single_source_fixtures"],0)
        self.assertEqual(out["matches"][0]["crosscheck_state"],"TWO_PUBLISHER_KICKOFF_AGREEMENT")
        self.assertFalse(out["six_league_results_independently_verified"])
        verify(out)

    def test_second_source_kickoff_conflict(self):
        o=secondary()
        o["sampled_fixtures"][0]["kickoff_utc"]=(NOW+timedelta(hours=5)).isoformat()
        out=crosscheck(german(),o,now=NOW)
        self.assertEqual(out["kickoff_disagreements_needing_review"],1)
        self.assertEqual(out["two_source_kickoff_agreements"],0)
        self.assertEqual(out["matches"][0]["crosscheck_state"],"KICKOFF_CONFLICT_REVIEW")
        verify(out)

    def test_missing_secondary_does_not_claim_double_verification(self):
        out=crosscheck(german(),None,now=NOW)
        self.assertFalse(out["schedule_crosscheck_completed"])
        self.assertEqual(out["unverified_single_source_fixtures"],1)
        verify(out)

    def test_old_secondary_does_not_boost_confidence(self):
        p=secondary()
        p["collected_utc"]=(NOW-timedelta(days=4)).isoformat()
        out=crosscheck(german(),p,now=NOW)
        self.assertEqual(out["two_source_kickoff_agreements"],0)
        self.assertEqual(out["unverified_single_source_fixtures"],1)

    def test_unsafe_secondary_cannot_promote_prediction(self):
        p=secondary()
        p["production_recommendations"]="ENABLED"
        out=crosscheck(german(),p,now=NOW)
        self.assertFalse(out["schedule_crosscheck_completed"])
        self.assertEqual(out["production_recommendations"],"DISABLED")

    def test_tampered_count_rejected(self):
        out=crosscheck(german(),secondary(),now=NOW)
        out["two_source_kickoff_agreements"]=2
        with self.assertRaisesRegex(ValueError,"LIVE_SOURCE_AUDIT_COUNTS_MISMATCH"):
            verify(out)


if __name__=="__main__":
    unittest.main()
