import sys
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from integrated_market_consensus import analyze

NOW=datetime(2026,10,9,14,0,tzinfo=timezone.utc)

def fixture():
    return {"fixture":{"home":"Home","away":"Away","league":"soccer_epl",
                       "event_id":"event-1","independent_fixture_sources":2}}

def odds():
    return [{"id":"event-1","sport_key":"soccer_epl",
             "home_team":"Home","away_team":"Away",
             "commence_time":"2026-10-09T13:00:00Z",
             "bookmakers":[
               {"key":"a","markets":[{"key":"totals",
                "last_update":"2026-10-09T13:59:45Z",
                "outcomes":[{"name":"Under","price":1.80,"point":1.75}]}]},
               {"key":"b","markets":[{"key":"totals",
                "last_update":"2026-10-09T13:59:40Z",
                "outcomes":[{"name":"Under","price":1.85,"point":1.75}]}]}]}]

class IntegratedTests(unittest.TestCase):
    def test_two_bookmaker_consensus_from_real_validator(self):
        r=analyze(fixture(),odds(),now=NOW)
        self.assertEqual(r["research_consensus_groups"],1)
        self.assertEqual(r["consensus_groups"][0]["bookmakers"],2)
        self.assertEqual(r["status"],"HOLD")
        self.assertFalse(r["can_execute_bet"])
        self.assertIsNone(r["recommendation"])

    def test_one_bookmaker_not_consensus(self):
        d=odds()
        d[0]["bookmakers"].pop()
        r=analyze(fixture(),d,now=NOW)
        self.assertEqual(r["research_consensus_groups"],0)

    def test_different_line_cannot_form_consensus(self):
        d=odds()
        d[0]["bookmakers"][1]["markets"][0]["outcomes"][0]["point"]=1.5
        self.assertEqual(analyze(fixture(),d,now=NOW)["research_consensus_groups"],0)

    def test_cross_match_id_cannot_form_consensus(self):
        d=odds()
        d[0]["id"]="another-id"
        r=analyze(fixture(),d,now=NOW)
        self.assertEqual(r["research_consensus_groups"],0)
        self.assertEqual(r["consensus_groups"],[])

    def test_stale_market_never_forms_consensus(self):
        d=odds()
        for book in d[0]["bookmakers"]:
            book["markets"][0]["last_update"]="2026-10-09T13:50:00Z"
        self.assertEqual(analyze(fixture(),d,now=NOW)["research_consensus_groups"],0)

    def test_no_fixture_never_joins(self):
        r=analyze({},odds(),now=NOW)
        self.assertEqual(r["research_consensus_groups"],0)
        self.assertEqual(r["status"],"HOLD")

    def test_untrusted_case_claims_cannot_unlock(self):
        c=fixture()
        c["market"]={"bookmaker_quote_executable_verified":True}
        r=analyze(c,odds(),now=NOW)
        self.assertIn("BOOKMAKER_EXECUTION_NOT_VERIFIED",r["blockers"])
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_future_quote_cannot_form_consensus(self):
        d=odds()
        for book in d[0]["bookmakers"]:
            book["markets"][0]["last_update"]="2026-10-09T14:05:00Z"
        self.assertEqual(analyze(fixture(),d,now=NOW)["research_consensus_groups"],0)


class IntegratedKickoffBindingTests(unittest.TestCase):
    def test_matching_utc_and_offset_instants_keep_existing_consensus(self):
        for kickoff in ("2026-10-09T13:00:00Z", "2026-10-09T21:00:00+08:00"):
            with self.subTest(kickoff=kickoff):
                case=fixture()
                case["fixture"]["kickoff_utc"]=kickoff
                report=analyze(case,odds(),now=NOW)
                self.assertEqual(report["fixture_kickoff_binding"],"MATCHED")
                self.assertEqual(len(report["research_quotes"]),2)
                self.assertEqual(report["research_consensus_groups"],1)
                self.assertTrue(report["decision"]["gate_checks"]["market_identity"])
                self.assertFalse(report["independent_source_confirmed"])
                self.assertFalse(report["can_execute_bet"])
                self.assertEqual(report["production_recommendations"],"DISABLED")

    def test_rescheduled_fixture_cannot_inherit_old_schedule_quotes(self):
        case=fixture()
        case["fixture"]["kickoff_utc"]="2026-10-10T13:00:00Z"
        case["market"]={"event_id":"event-1","league":"soccer_epl",
                        "market_key":"totals","validated_by_market_quote_gate":True,
                        "bookmaker_quote_executable_verified":True,
                        "last_update_utc":NOW.isoformat()}
        report=analyze(case,odds(),now=NOW)
        self.assertEqual(report["research_quotes"],[])
        self.assertEqual(report["consensus_groups"],[])
        self.assertEqual(report["research_consensus_groups"],0)
        self.assertEqual(report["fixture_kickoff_binding"],"NO_MATCHING_QUOTES")
        for check in ("market_identity","market_validated","market_clock","market_executable"):
            self.assertFalse(report["decision"]["gate_checks"][check])
        # Keep the raw-source audit for diagnostics, without associating quotes.
        self.assertEqual(report["market_audit"]["quotes_accepted"],2)

    def test_microsecond_schedule_change_does_not_get_rounded_into_match(self):
        case=fixture()
        case["fixture"]["kickoff_utc"]="2026-10-09T13:00:00.000001Z"
        report=analyze(case,odds(),now=NOW)
        self.assertEqual(report["research_quotes"],[])
        self.assertEqual(report["research_consensus_groups"],0)

    def test_explicit_invalid_time_cannot_downgrade_to_missing_legacy_time(self):
        for kickoff in (None,True,0,"","bad-time","2026-10-09T13:00:00",
                        "0001-01-01T00:00:00+01:00",
                        "9999-12-31T23:59:59-01:00"):
            with self.subTest(kickoff=kickoff):
                case=fixture()
                case["fixture"]["kickoff_utc"]=kickoff
                report=analyze(case,odds(),now=NOW)
                self.assertEqual(report["fixture_kickoff_binding"],"INVALID")
                self.assertEqual(report["research_quotes"],[])
                self.assertEqual(report["research_consensus_groups"],0)
                self.assertFalse(report["decision"]["gate_checks"]["market_validated"])

    def test_absent_kickoff_retains_explicit_legacy_research_contract(self):
        report=analyze(fixture(),odds(),now=NOW)
        self.assertEqual(report["fixture_kickoff_binding"],
                         "NOT_PROVIDED_LEGACY_RESEARCH_ONLY")
        self.assertEqual(report["research_consensus_groups"],1)
        self.assertFalse(report["independent_source_confirmed"])
        self.assertEqual(report["status"],"HOLD")

    def test_matching_kickoff_does_not_relax_native_event_id(self):
        case=fixture()
        case["fixture"]["kickoff_utc"]="2026-10-09T13:00:00Z"
        source=odds()
        source[0]["id"]="another-provider-event"
        report=analyze(case,source,now=NOW)
        self.assertEqual(report["fixture_kickoff_binding"],"NO_MATCHING_QUOTES")
        self.assertEqual(report["research_quotes"],[])
        self.assertEqual(report["consensus_groups"],[])

    def test_invalid_fixture_early_return_clears_self_declared_market(self):
        case=fixture()
        case["fixture"]["event_id"]=""
        case["fixture"]["kickoff_utc"]=None
        case["market"]={"event_id":"","league":"soccer_epl",
                        "market_key":"totals","validated_by_market_quote_gate":True,
                        "bookmaker_quote_executable_verified":True,
                        "last_update_utc":NOW.isoformat()}
        report=analyze(case,odds(),now=NOW)
        self.assertEqual(report["fixture_kickoff_binding"],"INVALID")
        self.assertEqual(report["research_quotes"],[])
        self.assertEqual(report["consensus_groups"],[])
        for check in ("market_validated","market_clock","market_executable"):
            self.assertFalse(report["decision"]["gate_checks"][check])

    def test_inputs_are_unchanged_on_matching_and_conflicting_kickoffs(self):
        for kickoff in ("2026-10-09T13:00:00Z","2026-10-10T13:00:00Z"):
            with self.subTest(kickoff=kickoff):
                case=fixture()
                case["fixture"]["kickoff_utc"]=kickoff
                source=odds()
                original_case,original_source=deepcopy(case),deepcopy(source)
                analyze(case,source,now=NOW)
                self.assertEqual(case,original_case)
                self.assertEqual(source,original_source)


if __name__=="__main__":
    unittest.main()
