"""Offline regressions for six-league two-publisher UTC fixture overlap."""
import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from six_league_fixture_overlap import SCHEMA, compare, validate

class SixLeagueOverlapTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,10,10,8,tzinfo=timezone.utc)
        self.market_time = self.now-timedelta(hours=2)
        self.source_time = self.now-timedelta(hours=3)
        self.ko = self.now + timedelta(days=1)
        self.fixture = dict(league="epl",home="Arsenal",away="Chelsea",
                            kickoff_utc=self.ko.isoformat(),
                            market_last_update_utc=(self.market_time-timedelta(minutes=2)).isoformat(),
                            source_event_id="match-key-1")
        self.market=dict(schema="football-king-market-consensus-v1",
                         status="RESEARCH_ONLY",production_recommendations="DISABLED",
                         as_of_utc=self.market_time.isoformat(),events=[self.fixture])
        self.row=dict(league="epl",home="Arsenal",away="Chelsea",
                      kickoff_utc=self.ko.isoformat(),provider="thesportsdb",
                      provider_event_id="provider-1",status="SCHEDULED")
        self.sources=dict(schema="football-king-extra-source-audit-v1",
                          sampled_fixtures=[self.row])

    def calc(self,m=None,s=None,now=None,source_clock=None):
        with patch("six_league_fixture_overlap.verify_sources",
                   return_value=source_clock or self.source_time):
            return compare(self.market if m is None else m,
                           self.sources if s is None else s,
                           captured_utc=(now or self.now).isoformat())

    def test_one_source_agreement(self):
        o=self.calc()
        self.assertTrue(validate(o))
        self.assertEqual(o["at_least_one_other_publisher_agreement"],1)
        self.assertEqual(o["at_least_two_other_publisher_agreements"],0)
        self.assertFalse(o["all_six_leagues_independently_verified"])
        self.assertFalse(o["model_promotion_authorized"])

    def test_two_distinct_publishers_not_two_bookmakers(self):
        d=copy.deepcopy(self.sources)
        other=copy.deepcopy(self.row)
        other["provider"]="football_data_org";other["provider_event_id"]="independent-2"
        d["sampled_fixtures"].append(other)
        o=self.calc(s=d)
        self.assertEqual(o["at_least_two_other_publisher_agreements"],1)
        self.assertTrue(o["other_publisher_not_independent_bookmaker"])
        self.assertEqual(o["independently_verified_final_results"],0)

    def test_same_publisher_duplicate_never_counts(self):
        d=copy.deepcopy(self.sources)
        d["sampled_fixtures"].append(copy.deepcopy(d["sampled_fixtures"][0]))
        o=self.calc(s=d)
        self.assertEqual(o["at_least_one_other_publisher_agreement"],0)
        self.assertGreater(o["ambiguous_or_duplicate_source_event_observations"],0)

    def test_conflict_blocks_per_match_even_with_agreement(self):
        d=copy.deepcopy(self.sources)
        other=copy.deepcopy(self.row);other["provider"]="football_data_org"
        other["kickoff_utc"]=(self.ko+timedelta(hours=2)).isoformat()
        d["sampled_fixtures"].append(other)
        o=self.calc(s=d)
        self.assertEqual(o["at_least_one_other_publisher_agreement"],0)
        self.assertEqual(o["source_schedule_conflict_observations"],1)

    def test_stale_source_does_not_claim_agreement(self):
        o=self.calc(source_clock=self.now-timedelta(days=3))
        self.assertEqual(o["status"],"HOLD")
        self.assertEqual(o["at_least_one_other_publisher_agreement"],0)
        self.assertFalse(o["secondary_fresh"])

    def test_stale_market_does_not_claim_agreement(self):
        m=copy.deepcopy(self.market)
        m["as_of_utc"]=(self.now-timedelta(days=2)).isoformat()
        o=self.calc(m=m)
        self.assertEqual(o["status"],"HOLD")
        self.assertFalse(o["market_fresh"])

    def test_kickoff_not_after_market_invalid(self):
        m=copy.deepcopy(self.market)
        m["events"][0]["kickoff_utc"]=(self.market_time+timedelta(minutes=5)).isoformat()
        o=self.calc(m=m)
        self.assertEqual(o["time_valid_market_count"],0)

    def test_missing_team_cannot_count(self):
        m=copy.deepcopy(self.market)
        m["events"][0]["home"]="unknown custom invented team name xyz"
        o=self.calc(m=m)
        self.assertEqual(o["time_valid_market_count"],0)

    def test_forged_pass_and_raw_quote_guard(self):
        o=self.calc()
        for k,v in (("model_promotion_authorized",True),
                    ("independently_verified_final_results",1),
                    ("original_bookmaker_quotes_stored",True)):
            forged=copy.deepcopy(o);forged[k]=v
            with self.assertRaises(ValueError):
                validate(forged)

if __name__=="__main__":
    unittest.main()
