"""Offline policy tests: synthetic operator scopes, zero provider calls."""
import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inplay_source_rights_preflight import (
    DEFAULT_WE_LEAGUE_PLAN, PROVIDERS, ROLES, audit, main,
)


class InplaySourceRightsPreflightTests(unittest.TestCase):
    def test_default_we_league_remains_hold_and_no_api_calls(self):
        result = audit(DEFAULT_WE_LEAGUE_PLAN)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["decision"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertEqual(result["certified_forward_samples"], 0)
        self.assertEqual(len(result["role_review"]), 5)
        self.assertEqual([x["role"] for x in result["role_review"]], list(ROLES))
        self.assertTrue(all(x["status"] == "BLOCKED" for x in result["role_review"]))
        for k in ("allow_network_collection", "allow_automatic_scraping",
                  "allow_raw_data_publication", "allow_betting",
                  "manual_legal_approval_record_verified",
                  "two_independent_live_scores_authenticated",
                  "market_inplay_coverage_verified", "market_executable_verified",
                  "trusted_tsa_identity_and_revocation_verified",
                  "positive_ev_verified", "model_scoring_eligible"):
            self.assertFalse(result[k], k)

    def test_fotmob_requires_written_consent(self):
        r = audit(DEFAULT_WE_LEAGUE_PLAN)
        self.assertIn("WRITTEN_FOTMOB_CONSENT_MISSING", r["blockers"])
        row = next(x for x in r["role_review"] if x["source"] == "fotmob")
        self.assertEqual(row["source_terms"], "https://www.fotmob.com/tos.txt")

    def test_we_league_official_rights_not_silently_granted(self):
        r = audit(DEFAULT_WE_LEAGUE_PLAN)
        self.assertIn("WE_LEAGUE_BULK_OR_API_REUSE_RIGHTS_MISSING", r["blockers"])

    def test_hkjc_quote_api_not_assumed(self):
        r = audit(DEFAULT_WE_LEAGUE_PLAN)
        self.assertIn("HKJC_AUTHORIZED_PROGRAMMATIC_MARKET_ACCESS_MISSING", r["blockers"])
        self.assertFalse(r["market_executable_verified"])

    def test_freetsa_is_candidate_not_an_authenticated_witness(self):
        r = audit(DEFAULT_WE_LEAGUE_PLAN)
        for reason in ("EXTERNAL_TSA_TOKEN_NOT_REQUESTED",
                       "TSA_CA_POLICY_REVOCATION_NOT_REVIEWED",
                       "BEST_EFFORT_TSA_NO_SLA"):
            self.assertIn(reason, r["blockers"])
        self.assertFalse(r["trusted_tsa_identity_and_revocation_verified"])

    def test_the_odds_api_we_league_coverage_not_proven(self):
        p = dict(DEFAULT_WE_LEAGUE_PLAN, market="the_odds_api_v4")
        r = audit(p)
        self.assertIn("WE_LEAGUE_NOT_DOCUMENTED_IN_PUBLIC_SPORTS_LIST", r["blockers"])
        self.assertIn("HKJC_THREE_WAY_CONTRACT_NOT_DOCUMENTED_IN_API", r["blockers"])
        self.assertIn("API_PLAN_AND_MARKET_ENTITLEMENT_UNVERIFIED", r["blockers"])

    def test_the_odds_api_j_league_general_research_is_not_executable(self):
        p = dict(DEFAULT_WE_LEAGUE_PLAN, market="the_odds_api_v4")
        r = audit(p, league="japan_j_league", market="H2H_1X2")
        self.assertNotIn("WE_LEAGUE_NOT_DOCUMENTED_IN_PUBLIC_SPORTS_LIST", r["blockers"])
        self.assertNotIn("HKJC_THREE_WAY_CONTRACT_NOT_DOCUMENTED_IN_API", r["blockers"])
        self.assertIn("API_PLAN_AND_MARKET_ENTITLEMENT_UNVERIFIED", r["blockers"])
        self.assertFalse(r["allow_network_collection"])
        self.assertFalse(r["market_executable_verified"])

    def test_same_score_provider_is_not_independence(self):
        p = dict(DEFAULT_WE_LEAGUE_PLAN, score_secondary="we_league_official")
        r = audit(p)
        self.assertIn("DUPLICATE_SCORE_PUBLISHER", r["blockers"])
        self.assertFalse(r["two_independent_live_scores_authenticated"])

    def test_different_score_names_are_still_not_proven_independent(self):
        r = audit(DEFAULT_WE_LEAGUE_PLAN)
        self.assertIn("INDEPENDENT_SCORE_COLLECTION_NOT_ATTESTED", r["blockers"])

    def test_role_mismatch_never_promotes_the_odds_api_score_feed(self):
        p = dict(DEFAULT_WE_LEAGUE_PLAN, score_secondary="the_odds_api_v4")
        r = audit(p)
        self.assertIn("PROVIDER_NOT_APPROVED_FOR_ROLE", r["blockers"])
        self.assertEqual(r["status"], "HOLD")

    def test_unknown_provider_fails_without_fallback(self):
        p = dict(DEFAULT_WE_LEAGUE_PLAN, market="some_rumoured_odds_feed")
        r = audit(p)
        self.assertEqual(r["blockers"], ["UNKNOWN_OR_UNTRUSTED_PROVIDER"])
        self.assertEqual(r["role_review"], [])

    def test_unsupported_league_market_and_fractional_handicap_rejected(self):
        for league, market in (("japan_we_league_2026", "H2H_1X2"),
                               ("japan_we_league", "HKJC_ASIAN_-0.75"),
                               ("japan_we_league", "WIN_PROBABILITY_ONLY"),
                               ("WE_League", "HKJC_THREE_WAY_HANDICAP")):
            r = audit(DEFAULT_WE_LEAGUE_PLAN, league=league, market=market)
            self.assertEqual(r["blockers"], ["INVALID_PILOT_SCOPE_OR_PLAN"])
            self.assertFalse(r["allow_network_collection"])

    def test_untrusted_approval_fields_cannot_unlock_permissions(self):
        payload = dict(DEFAULT_WE_LEAGUE_PLAN, approved=True)
        self.assertEqual(audit(payload)["blockers"], ["INVALID_PILOT_SCOPE_OR_PLAN"])
        p = dict(DEFAULT_WE_LEAGUE_PLAN, market={"source": "hkjc", "approved": True})
        self.assertEqual(audit(p)["blockers"], ["UNKNOWN_OR_UNTRUSTED_PROVIDER"])

    def test_bool_null_and_list_do_not_bypass_scope(self):
        for invalid in (True, None, [], {"fake": "source"}, 1):
            self.assertEqual(audit(invalid)["status"], "HOLD")
            self.assertFalse(audit(invalid)["model_scoring_eligible"])

    def test_input_not_mutated_and_repeat_deterministic(self):
        p = copy.deepcopy(DEFAULT_WE_LEAGUE_PLAN)
        baseline = copy.deepcopy(p)
        a, b = audit(p), audit(p)
        self.assertEqual(p, baseline)
        self.assertEqual(a, b)
        self.assertEqual(list(PROVIDERS), [
            "we_league_official", "fotmob", "hkjc", "the_odds_api_v4", "freetsa"])

    def test_cli_default_prints_only_metadata_and_exits_closed(self):
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = main([])
        r = json.loads(out.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["certified_forward_samples"], 0)
        self.assertNotIn("api_key", out.getvalue().lower())

    def test_pinned_evidence_uris_are_public_https(self):
        for p in PROVIDERS.values():
            self.assertTrue(p["evidence"].startswith("https://"))
            self.assertNotIn("token=", p["evidence"])


if __name__ == "__main__":
    unittest.main()
