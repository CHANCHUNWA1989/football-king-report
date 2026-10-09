"""Zero-credit monitoring of real source gaps without inventing model quality."""
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from system_health import analyze

NOW=datetime(2026,10,9,13,tzinfo=timezone.utc)


def sample():
    pred=NOW-timedelta(hours=1)
    ko=NOW+timedelta(days=2)
    return {
        "league":"epl", "home":"Arsenal", "away":"Everton",
        "prediction_utc":pred.isoformat(), "market_snapshot_utc":(pred-timedelta(minutes=10)).isoformat(),
        "kickoff_utc":ko.isoformat(),"production_recommendations":"DISABLED",
        "model":[.5,.25,.25],"market":[.45,.3,.25]
    }


def fixtures():
    row=sample()
    return {
        "evidence":{"n":0,"samples":[],"production_recommendations":"DISABLED"},
        "market":{"as_of_utc":(NOW-timedelta(hours=3)).isoformat(),
                  "events":[{"league":"epl"}],
                  "quota":{"remaining":476},"production_recommendations":"DISABLED"},
        "secondary":{"collected_utc":(NOW-timedelta(hours=2)).isoformat(),
                     "providers":[{"provider":"thesportsdb","status":"PARTIAL_COVERAGE",
                                   "configured":True},
                                  {"provider":"football_data_org","status":"NOT_CONFIGURED",
                                   "configured":False}],
                     "sampled_fixtures":[{"league":"epl"}],
                     "production_recommendations":"DISABLED"},
        "wide":{"collected_utc":(NOW-timedelta(hours=3)).isoformat(),
                "providers":[{"provider":"openligadb","status":"PARTIAL_COVERAGE",
                              "configured":True}],
                "production_recommendations":"DISABLED"},
        "extensions":{"completed_utc":NOW.isoformat(),
                      "providers":[{"provider":"statsbomb_open_data",
                                    "status":"HISTORICAL_CATALOG_READY",
                                    "configured":True}],
                      "production_recommendations":"DISABLED"},
        "archived":[(("epl","arsenal","everton",row["kickoff_utc"]),row)],
        "now":NOW,
    }


class OperationalHealthTests(unittest.TestCase):
    def test_no_sample_means_hold_and_actionable_reasons(self):
        r=analyze(**fixtures())
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["settled_forward_cases"],0)
        self.assertEqual(r["archived_waiting_kickoff"],1)
        self.assertEqual(r["archived_past_kickoff_not_settled"],0)
        self.assertIn("NO_SETTLED_OUT_OF_SAMPLE_CASES",r["attention_reasons"])
        self.assertIn("AT_LEAST_ONE_LEAGUE_MISSING_1X2_MARKET",r["attention_reasons"])
        self.assertIn("OPTIONAL_FREE_PROVIDERS_MISSING_COVERAGE",r["attention_reasons"])
        self.assertEqual(r["market_free_quota_remaining"],476)
        self.assertTrue(r["zero_extra_api_calls"])
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_old_kickoff_without_settlement_gets_separate_diagnosis(self):
        d=fixtures()
        item=sample()
        item["kickoff_utc"]=(NOW-timedelta(days=1)).isoformat()
        d["archived"]=[(("epl","arsenal","everton",item["kickoff_utc"]),item)]
        r=analyze(**d)
        self.assertEqual(r["archived_past_kickoff_not_settled"],1)
        self.assertIn("FINISHED_KICKOFF_ARCHIVES_AWAIT_SCORE_SETTLEMENT",r["attention_reasons"])

    def test_stale_market_does_not_pretend_live(self):
        d=fixtures()
        d["market"]["as_of_utc"]=(NOW-timedelta(days=4)).isoformat()
        x=analyze(**d)
        self.assertEqual(x["source_snapshot_health"]["market"]["status"],"STALE_OR_FUTURE")
        self.assertIn("ONE_OR_MORE_STALE_OR_UNKNOWN_SOURCE_SNAPSHOTS",x["attention_reasons"])

    def test_conflicting_evidence_sample_count_fails_closed(self):
        d=fixtures()
        d["evidence"]["n"]=1
        with self.assertRaisesRegex(ValueError,"BROKEN_SETTLEMENT_COUNT"):
            analyze(**d)

    def test_unsafe_free_source_betting_permission_fails_closed(self):
        d=fixtures()
        d["secondary"]["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"UNSAFE_MONITOR_SOURCE"):
            analyze(**d)

    def test_archive_identity_collision_fails_closed(self):
        d=fixtures()
        d["archived"].append(d["archived"][0])
        with self.assertRaisesRegex(ValueError,"DUPLICATE_ARCHIVED_CASE"):
            analyze(**d)

    def test_missing_market_quota_prompts_attention_not_fake_balance(self):
        d=fixtures()
        d["market"]["quota"]={}
        r=analyze(**d)
        self.assertIsNone(r["market_free_quota_remaining"])
        self.assertIn("MARKET_FREE_CREDIT_RESERVE_UNKNOWN_OR_LOW",r["attention_reasons"])

    def test_all_six_league_coverage_is_not_trusted_as_independent(self):
        d=fixtures()
        d["market"]["events"]=[{"league":lg} for lg in (
            "epl","championship","bundesliga","laliga","seriea","ligue1")]
        r=analyze(**d)
        self.assertNotIn("AT_LEAST_ONE_LEAGUE_MISSING_1X2_MARKET",r["attention_reasons"])
        self.assertFalse(r["results_independently_verified"])
        self.assertFalse(r["market_bookmaker_quotes_are_executable"])
        self.assertFalse(r["model_probabilities_rewritten"])


if __name__=="__main__":
    unittest.main()
