import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import freeze_versioned_pricing_evidence
from ops.research_historic_source_snapshot_v1 import prepare_historic_source_snapshot
from ops.research_historic_replay_policy_v1 import historical_replay_plan,REQUIRED_CONTROLS
from ops.research_historic_replay_handoff_v1 import create_historic_replay_handoff
from ops.research_historic_replay_preflight_v1 import (
    historical_replay_preflight,verify_historical_replay_preflight)

class HistoricReplayPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        now=datetime(2026,11,27,12,tzinfo=timezone.utc)
        quotes=[]
        for market,selection,line in (
            ("handicap","home",-0.25),("handicap","away",-0.25),
            ("totals","over",2.5),("totals","under",2.5)):
            for source,upstream in (("a","up-a"),("b","up-b")):
                quotes.append(Quote(source=source,upstream_provider=upstream,
                    bookmaker="book-a",event_id="fixture",market=market,
                    selection=selection,line=line,decimal_odds=1.91,
                    observed_at=now-timedelta(seconds=20),
                    kickoff_at=now+timedelta(hours=1)))
        cls.record=freeze_versioned_pricing_evidence(
            event_id="fixture",home_xg=1.5,away_xg=1.1,quotes=quotes,
            now=now,handicap_line=-0.25,totals_line=2.5)
        cls.snapshot=prepare_historic_source_snapshot(
            cls.record,historic_root=".")["snapshot"]
        cls.plan=historical_replay_plan(cls.record,historic_root=".")
        cls.handoff=create_historic_replay_handoff(
            snapshot=cls.snapshot,record=cls.record,plan=cls.plan)
    def run_preflight(self,**kwargs):
        return historical_replay_preflight(
            handoff=self.handoff,snapshot=self.snapshot,
            record=self.record,plan=self.plan,**kwargs)
    def test_missing_claims_fail_closed(self):
        p=self.run_preflight()
        self.assertEqual(p["reason"],"EXECUTOR_CONTROLS_NOT_MATCHED")
        self.assertFalse(p["execution_permitted"])
    def test_matching_claims_still_not_attested(self):
        p=self.run_preflight(executor_claims=dict(REQUIRED_CONTROLS))
        self.assertEqual(p["reason"],"OS_ISOLATION_UNATTESTED")
        self.assertTrue(p["executor_claims_match_policy"])
        self.assertFalse(p["os_isolation_verified"])
        self.assertFalse(p["execution_permitted"])
        self.assertTrue(verify_historical_replay_preflight(
            p,handoff=self.handoff,snapshot=self.snapshot,
            record=self.record,plan=self.plan,executor_claims=dict(REQUIRED_CONTROLS)))
    def test_invalid_handoff_rejected(self):
        p=self.run_preflight(executor_claims=dict(REQUIRED_CONTROLS))
        bad=dict(self.handoff)
        bad["sha256"]="0"*64
        rejected=historical_replay_preflight(
            handoff=bad,snapshot=self.snapshot,record=self.record,
            plan=self.plan,executor_claims=dict(REQUIRED_CONTROLS))
        self.assertEqual(rejected["reason"],"INVALID_HANDOFF")
    def test_wrong_control_type_rejected(self):
        claims=dict(REQUIRED_CONTROLS)
        claims["production_access"]=0
        self.assertEqual(self.run_preflight(executor_claims=claims)["reason"],
                         "EXECUTOR_CONTROLS_NOT_MATCHED")
    def test_modified_result_rejected(self):
        p=self.run_preflight()
        p["execution_permitted"]=True
        self.assertFalse(verify_historical_replay_preflight(
            p,handoff=self.handoff,snapshot=self.snapshot,
            record=self.record,plan=self.plan))
if __name__=="__main__":unittest.main()
