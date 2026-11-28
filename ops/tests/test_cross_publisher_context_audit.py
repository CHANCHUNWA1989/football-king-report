import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from ops.fixture_source_evidence import capture_batch, assemble
from ops.cross_publisher_context_audit import audit

NOW=datetime(2026,11,28,8,tzinfo=timezone.utc)
KO="2026-11-28T12:00:00+00:00"


class CrossPublisherContextAuditTests(unittest.TestCase):
    def gateway(self, rows):
        raw={"league":"epl","status":"READY_RESEARCH","source":"openfootball/football.json",
             "source_url":"https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/en.1.json",
             "captured_utc":"2026-11-28T07:59:00+00:00","matches":rows}
        return assemble([capture_batch("epl","2026-27",raw,NOW,replay=False)],NOW)

    def row(self, **kw):
        return {"date":"2026-11-28","home":"Arsenal FC","away":"Everton FC",
                "status":"UNCONFIRMED",**kw}

    def secondary(self, **kw):
        a={"league":"epl","home":"Arsenal","away":"Everton","status":"SCHEDULED",
           "kickoff_utc":KO,"score_ft":None,"provider":"thesportsdb","provider_event_id":"1"}
        b=dict(a,provider="football_data_org",provider_event_id="2",**{})
        b.update(kw)
        return {"status":"RESEARCH_ONLY","providers":[
            {"provider":p,"configured":True,"status":"PARTIAL","sampled_fixture_count":1}
            for p in ("thesportsdb","football_data_org")],"sampled_fixtures":[a,b]}

    def run_audit(self, gateway, secondary):
        # Isolate matching rules; full secondary schema guard tested separately.
        with patch("ops.cross_publisher_context_audit.verify",return_value=NOW):
            return audit(gateway,secondary)

    def test_exact_alias_date_context_not_identity_admission(self):
        r=self.run_audit(self.gateway([self.row()]),self.secondary())
        self.assertEqual(r["counts"],{"DATE_ONLY_CONTEXT_MATCH":1})
        self.assertFalse(r["native_identity_authenticated"])
        self.assertEqual(r["admitted_new_fixtures"],0)

    def test_utc_agreement_and_conflict(self):
        self.assertEqual(self.run_audit(self.gateway([self.row(kickoff_utc=KO)]),self.secondary())["counts"],
                         {"EXACT_UTC_CONTEXT_MATCH":1})
        self.assertEqual(self.run_audit(self.gateway([self.row()]),self.secondary(kickoff_utc="2026-11-28T12:01:00Z"))["counts"],
                         {"SECONDARY_UTC_CONFLICT":1})

    def test_no_projection_never_proves_missing_fixture(self):
        r=self.run_audit(self.gateway([]),self.secondary())
        self.assertEqual(r["counts"],{"NO_MATCH_IN_CAPTURED_PROJECTION":1})
        self.assertFalse(r["missing_gateway_fixtures_proven"])

    def test_reverse_direction_and_ambiguous_context(self):
        r=self.run_audit(self.gateway([self.row(home="Everton",away="Arsenal")]),self.secondary())
        self.assertEqual(r["counts"],{"GATEWAY_OPPONENT_OR_DIRECTION_CONFLICT":1})
        r=self.run_audit(self.gateway([self.row(),self.row()]),self.secondary())
        self.assertEqual(r["counts"],{"GATEWAY_AMBIGUOUS":1})

    def test_duplicate_and_single_publisher(self):
        r=self.run_audit(self.gateway([self.row()]),self.secondary(provider="thesportsdb"))
        self.assertEqual(r["counts"],{"DUPLICATE_PROVIDER_VOTE":1})
        s=self.secondary()
        s["sampled_fixtures"].pop()
        self.assertEqual(self.run_audit(self.gateway([self.row()]),s)["counts"],{"SINGLE_PROVIDER":1})
