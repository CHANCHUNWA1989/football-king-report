import unittest
from datetime import datetime,timedelta,timezone
from ops.research_market_provenance_v1 import Quote
from ops.research_model_source_binding_v1 import freeze_versioned_pricing_evidence
from ops.research_historic_replay_policy_v1 import (
    historical_replay_plan,verify_historical_replay_plan)

class HistoricReplayPolicyTests(unittest.TestCase):
    def setUp(self):
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
        self.record=freeze_versioned_pricing_evidence(
            event_id="fixture",home_xg=1.5,away_xg=1.1,quotes=quotes,
            now=now,handicap_line=-0.25,totals_line=2.5)
    def test_valid_plan_stays_disabled(self):
        plan=historical_replay_plan(self.record,historic_root=".")
        self.assertTrue(verify_historical_replay_plan(plan))
        self.assertEqual(plan["reason"],"SOURCE_BYTES_MATCH_BUT_SANDBOX_NOT_CONFIGURED")
        self.assertFalse(plan["execution_permitted"])
        self.assertEqual(plan["required_controls"]["network"],"none")
    def test_missing_source_rejected(self):
        plan=historical_replay_plan(self.record,historic_root="/nonexistent/football-king")
        self.assertEqual(plan["reason"],"SOURCE_ATTESTATION_FAILED")
        self.assertFalse(plan["execution_permitted"])
    def test_policy_tampering_rejected(self):
        plan=historical_replay_plan(self.record,historic_root=".")
        plan["required_controls"]["network"]="host"
        self.assertFalse(verify_historical_replay_plan(plan))
    def test_cannot_enable_execution(self):
        plan=historical_replay_plan(self.record,historic_root=".")
        plan["execution_permitted"]=True
        self.assertFalse(verify_historical_replay_plan(plan))
if __name__=="__main__":unittest.main()
