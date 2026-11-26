import unittest
from datetime import datetime,timedelta,timezone
from live_core_unified_schedule_consensus import review
from live_core_same_batch_collection import run
import test_six_league_free_upgrade as existing

class UnifiedScheduleConsensusTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,26,12,tzinfo=timezone.utc)
        self.s={"league":"bundesliga","home_id":"a","away_id":"b","native_id":"1",
                "kickoff_utc":(self.now+timedelta(days=1)).isoformat(),"received_utc":self.now.isoformat()}
        self.m=dict(self.s,oldest_market_update_utc=self.now.isoformat())
    def audit(self,s,o,f,markets=None):
        return review([self.m] if markets is None else markets,s,o,f,finished=self.now)
    def test_three_names_not_independent(self):
        r=self.audit([self.s],[self.s],[self.s])
        self.assertEqual(r["disposition"]["THREE_SCHEDULE_LABELS_AGREE"],1)
        self.assertFalse(r["source_independence_verified"])
        self.assertEqual(r["authenticated_forward_samples"],0)
    def test_conflict_overrides_two_agreements(self):
        c=dict(self.s,kickoff_utc=(self.now+timedelta(days=2)).isoformat())
        r=self.audit([self.s],[self.s],[c])
        self.assertEqual(r["disposition"]["SOURCE_CONFLICT_OR_AMBIGUITY"],1)
        self.assertEqual(r["disposition"]["TWO_SCHEDULE_LABELS_AGREE"],0)
    def test_duplicates_and_stale_block(self):
        self.assertEqual(self.audit([self.s],[self.s,self.s],[])["disposition"]["SOURCE_CONFLICT_OR_AMBIGUITY"],1)
        old=dict(self.s,received_utc=(self.now-timedelta(minutes=21)).isoformat())
        self.assertEqual(self.audit([self.s],[old],[])["disposition"]["STALE_SOURCE_MATCH"],1)
    def test_expired_market_and_denominator(self):
        m=dict(self.m,oldest_market_update_utc=(self.now-timedelta(minutes=21)).isoformat())
        r=self.audit([self.s],[self.s],[self.s],markets=[m])
        self.assertEqual(r["disposition"]["MARKET_TIME_REJECTED"],1)
        self.assertEqual(sum(r["disposition"].values()),1)
        self.assertEqual(r["rows_checked_against_sources"],0)
    def test_same_process_no_credentials(self):
        f=existing.SixFreeUpgradeTests();f.setUp()
        _,o,g=run(token="",now=lambda:f.now,fixed_now=f.now)
        r=o["unified_schedule_consensus_research"]
        self.assertEqual(r["market_rows"],0);self.assertEqual(sum(r["disposition"].values()),0)
        self.assertFalse(g["can_promote_model"])
    def test_cross_league_scope(self):
        with self.assertRaises(ValueError):
            self.audit([], [dict(self.s,league="epl")],[])
