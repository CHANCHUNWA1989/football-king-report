"""Market archiving must be monotonic, minimal and never include raw prices."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from market_archive_guard import latest_can_replace, check


class MarketArchiveTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,9,5,tzinfo=timezone.utc)
        self.sample={
            "schema":"football-king-market-consensus-v1",
            "provider":"the-odds-api.com/v4","status":"RESEARCH_ONLY",
            "as_of_utc":self.now.isoformat(),
            "event_count":1,
            "events":[{
                "league":"epl","source_event_id":"f1","home":"A","away":"B",
                "kickoff_utc":(self.now+timedelta(days=1)).isoformat(),
                "market_last_update_utc":(self.now-timedelta(minutes=2)).isoformat(),
                "contributing_bookmakers":3,
                "p_home":.4,"p_draw":.3,"p_away":.3,
                "probabilities_are_no_vig_consensus":True,
                "prediction_or_value_bet":False}],
            "raw_bookmaker_quotes_redistributed":False,
            "production_recommendations":"DISABLED",
        }

    def test_new_snapshot_overwrites_old(self):
        old={**self.sample,"as_of_utc":(self.now-timedelta(hours=1)).isoformat(),
             "events":[{**self.sample["events"][0],
                        "market_last_update_utc":(self.now-timedelta(hours=2)).isoformat()}]}
        self.assertTrue(latest_can_replace(old,self.sample))

    def test_stale_does_not_overwrite(self):
        newer={**self.sample,"as_of_utc":(self.now+timedelta(minutes=1)).isoformat()}
        self.assertFalse(latest_can_replace(newer,self.sample))

    def test_exact_repeat_is_idempotent(self):
        self.assertFalse(latest_can_replace(self.sample,self.sample))

    def test_no_raw_bookmaker_prices(self):
        self.sample["events"][0]["price"]=1.8
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED_MARKET_FIELDS"):
            check(self.sample)

    def test_inplay_rejected(self):
        self.sample["events"][0]["kickoff_utc"]=(self.now-timedelta(minutes=4)).isoformat()
        with self.assertRaisesRegex(ValueError,"LIVE_OR_FINISHED"):
            check(self.sample)

    def test_conflicting_same_time_is_rejected(self):
        old={**self.sample,"reason":"different version"}
        with self.assertRaisesRegex(ValueError,"SAME_CAPTURE_CONFLICT"):
            latest_can_replace(old,self.sample)

    def test_invalid_provider_fails(self):
        self.sample["provider"]="unauthorized"
        with self.assertRaisesRegex(ValueError,"INVALID_MARKET_METADATA"):
            check(self.sample)

    def test_invalid_prediction_flag_fails(self):
        self.sample["events"][0]["prediction_or_value_bet"]=True
        with self.assertRaisesRegex(ValueError,"INVALID_BOOKMAKER_RESEARCH"):
            check(self.sample)

    def test_market_probabilities_must_sum_to_one(self):
        self.sample["events"][0]["p_home"]=.8
        with self.assertRaisesRegex(ValueError,"INVALID_MARKET_PROBABILITIES"):
            check(self.sample)


if __name__=="__main__":
    unittest.main()
