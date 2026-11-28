import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import freeze_versioned_pricing_evidence
from ops.research_historic_source_snapshot_v1 import prepare_historic_source_snapshot
from ops.research_historic_replay_policy_v1 import historical_replay_plan
from ops.research_historic_replay_handoff_v1 import create_historic_replay_handoff
from ops.research_unified_historic_admission_v1 import (
    unified_historic_admission,verify_unified_historic_admission)

class UnifiedHistoricAdmissionTests(unittest.TestCase):
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
    def report(self):
        return {"schema":"football-king-historic-executor-report-v1",
                "handoff_sha256":self.handoff["sha256"],"exit_code":0,
                "stdout_sha256":"a"*64,"stderr_sha256":"b"*64,
                "claimed_isolation":True}
    def admit(self,report=None,handoff=None):
        return unified_historic_admission(
            record=self.record,snapshot=self.snapshot,plan=self.plan,
            handoff=self.handoff if handoff is None else handoff,
            report=self.report() if report is None else report)
    def test_complete_chain_not_production(self):
        result=self.admit()
        self.assertEqual(result["reason"],"NO_INDEPENDENT_OS_ATTESTATION")
        self.assertTrue(result["handoff_verified"])
        self.assertFalse(result["execution_permitted"])
        self.assertFalse(result["historic_replay_verified"])
    def test_report_tamper_fails(self):
        report=self.report()
        report["stdout_sha256"]="invalid"
        self.assertEqual(self.admit(report=report)["reason"],"INVALID_EXECUTOR_REPORT")
    def test_handoff_tamper_fails(self):
        handoff=dict(self.handoff)
        handoff["sha256"]="0"*64
        self.assertEqual(self.admit(handoff=handoff)["reason"],"INVALID_HANDOFF")
    def test_forged_admission_rejected(self):
        result=self.admit()
        result["qualified_for_production"]=True
        self.assertFalse(verify_unified_historic_admission(
            result,record=self.record,snapshot=self.snapshot,
            plan=self.plan,handoff=self.handoff,report=self.report()))
if __name__=="__main__":unittest.main()
