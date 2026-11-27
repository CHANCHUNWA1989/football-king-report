import copy
import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import freeze_versioned_pricing_evidence
from ops.research_historic_source_snapshot_v1 import prepare_historic_source_snapshot
from ops.research_historic_replay_policy_v1 import historical_replay_plan
from ops.research_historic_replay_handoff_v1 import (
    create_historic_replay_handoff,verify_historic_replay_handoff)

class HistoricReplayHandoffTests(unittest.TestCase):
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
    def handoff(self):
        return create_historic_replay_handoff(
            snapshot=self.snapshot,record=self.record,plan=self.plan)
    def test_valid_handoff_is_non_executable(self):
        envelope=self.handoff()
        self.assertTrue(verify_historic_replay_handoff(
            envelope,snapshot=self.snapshot,record=self.record,plan=self.plan))
        self.assertFalse(envelope["execution_permitted"])
    def test_mismatched_snapshot_fails(self):
        envelope=self.handoff()
        snapshot=copy.deepcopy(self.snapshot)
        snapshot["sha256"]="0"*64
        self.assertFalse(verify_historic_replay_handoff(
            envelope,snapshot=snapshot,record=self.record,plan=self.plan))
    def test_policy_mutation_fails(self):
        envelope=self.handoff()
        plan=copy.deepcopy(self.plan)
        plan["required_controls"]["network"]="host"
        self.assertFalse(verify_historic_replay_handoff(
            envelope,snapshot=self.snapshot,record=self.record,plan=plan))
    def test_handoff_execution_override_fails(self):
        envelope=self.handoff()
        envelope["execution_permitted"]=True
        self.assertFalse(verify_historic_replay_handoff(
            envelope,snapshot=self.snapshot,record=self.record,plan=self.plan))
    def test_archive_mismatch_fails(self):
        envelope=self.handoff()
        record=copy.deepcopy(self.record)
        record["sha256"]="0"*64
        self.assertFalse(verify_historic_replay_handoff(
            envelope,snapshot=self.snapshot,record=record,plan=self.plan))
if __name__=="__main__":unittest.main()
