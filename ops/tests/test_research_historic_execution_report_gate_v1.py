import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import freeze_versioned_pricing_evidence
from ops.research_historic_source_snapshot_v1 import prepare_historic_source_snapshot
from ops.research_historic_replay_policy_v1 import historical_replay_plan
from ops.research_historic_replay_handoff_v1 import create_historic_replay_handoff
from ops.research_historic_execution_report_gate_v1 import assess_historic_execution_report

class HistoricExecutionReportGateTests(unittest.TestCase):
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
    def assess(self,report):
        return assess_historic_execution_report(
            report=report,handoff=self.handoff,snapshot=self.snapshot,
            record=self.record,plan=self.plan)
    def test_success_claim_not_attestation(self):
        result=self.assess(self.report())
        self.assertEqual(result["reason"],"UNTRUSTED_EXECUTOR_REPORT_NO_OS_ATTESTATION")
        self.assertTrue(result["report_structurally_valid"])
        self.assertFalse(result["historic_replay_verified"])
        self.assertFalse(result["execution_permitted"])
    def test_wrong_handoff_rejected(self):
        report=self.report()
        report["handoff_sha256"]="0"*64
        self.assertEqual(self.assess(report)["reason"],"INVALID_EXECUTOR_REPORT")
    def test_extra_fields_rejected(self):
        report=self.report()
        report["allow_execution"]=True
        self.assertEqual(self.assess(report)["reason"],"INVALID_EXECUTOR_REPORT")
    def test_invalid_digest_rejected(self):
        report=self.report()
        report["stdout_sha256"]="NOT-A-DIGEST"
        self.assertEqual(self.assess(report)["reason"],"INVALID_EXECUTOR_REPORT")
    def test_bool_exit_code_rejected(self):
        report=self.report()
        report["exit_code"]=True
        self.assertEqual(self.assess(report)["reason"],"INVALID_EXECUTOR_REPORT")
if __name__=="__main__":unittest.main()
