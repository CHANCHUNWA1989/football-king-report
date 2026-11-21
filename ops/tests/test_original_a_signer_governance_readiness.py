"""Synthetic adversarial governance readiness tests. No admin credentials."""
import copy
import io
import json
from unittest.mock import patch
from urllib.error import HTTPError
import unittest

from ops.original_a_signer_governance_readiness import (
    REPO, REPO_ID, ENDPOINTS, SIGNER, REQUIRED, ACTIONS_APP_ID,
    ReadUnavailable, github_reader, snapshot, assess, main,
)

MAIN_SHA = "a" * 40
PR_SHA = "b" * 40


def trusted():
    return {
        "branch": {"name":"main", "protected":True, "commit":{"sha":MAIN_SHA}},
        "protection": {
            "required_pull_request_reviews":{
                "required_approving_review_count":1,
                "dismiss_stale_reviews":True,
                "require_last_push_approval":True},
            "enforce_admins":{"enabled":True},
            "required_status_checks":{
                "strict":True,
                "checks":[{"context":key,"app_id":ACTIONS_APP_ID} for key in sorted(REQUIRED)]},
            "allow_force_pushes":{"enabled":False},
            "allow_deletions":{"enabled":False},
        },
        "rulesets":[],
        "signer_workflow":{
            "path":SIGNER,"type":"file","sha":"c"*40,"size":4500},
        "pr":{
            "number":458,"state":"open","draft":False,"merged":False,
            "head":{"sha":PR_SHA},"user":{"login":"repo-owner","type":"User"},
        },
        "reviews":[{
            "user":{"login":"independent-human","type":"User"},
            "state":"APPROVED","commit_id":PR_SHA,
        }],
    }


def ctx():
    return {
        "GITHUB_REPOSITORY":REPO,
        "GITHUB_REPOSITORY_ID":REPO_ID,
        "GITHUB_EVENT_NAME":"workflow_dispatch",
        "GITHUB_REF":"refs/heads/main",
        "GITHUB_REF_TYPE":"branch",
        "GITHUB_SHA":MAIN_SHA,
    }


class GovernanceReadinessTests(unittest.TestCase):
    def ready(self,data=None,context=None):
        return assess(trusted() if data is None else data,
                      context=ctx() if context is None else context)

    def held(self,report,reason=None):
        self.assertEqual(report["status"],"HOLD")
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertFalse(report["approved_main_signer_enabled"])
        self.assertFalse(report["real_signatures_verified"])
        self.assertFalse(report["actual_live_capture_authorized"])
        self.assertFalse(report["data_rights_verified"])
        self.assertFalse(report["independently_verified_results"])
        self.assertFalse(report["model_promoted"])
        self.assertFalse(report["positive_ev_verified"])
        self.assertEqual(report["certified_prospective_samples"],0)
        if reason:
            self.assertIn(reason, report["governance_blocker_codes"])

    def test_synthetic_compliant_governance_still_cannot_enable_signing(self):
        r=self.ready()
        self.held(r)
        self.assertEqual(r["governance_blocker_codes"],[])
        self.assertTrue(r["governance_preflight_requirements_observed"])
        self.assertEqual(r["main_commit_observed"],MAIN_SHA)

    def test_current_reality_unprotected_main_is_hold(self):
        d=trusted()
        d["branch"]["protected"]=False
        d["protection"]={"_error":"GITHUB_ADMIN_READ_FORBIDDEN"}
        d["rulesets"]=[]
        d["signer_workflow"]={"_error":"GITHUB_RESOURCE_NOT_FOUND"}
        d["pr"]["draft"]=True
        d["reviews"]=[]
        r=self.ready(d)
        self.held(r,"MAIN_NOT_PROTECTED")
        for code in ("PROTECTION_READ_UNAVAILABLE",
                     "APPROVED_MAIN_SIGNER_WORKFLOW_ABSENT",
                     "CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING",
                     "RESEARCH_PR_NOT_READY_FOR_APPROVAL"):
            self.assertIn(code,r["governance_blocker_codes"])
        self.assertFalse(r["governance_preflight_requirements_observed"])

    def test_missing_branch_response_fails_closed(self):
        d=trusted();d["branch"]={"_error":"GITHUB_READ_UNAVAILABLE"}
        self.held(self.ready(d),"MAIN_BRANCH_METADATA_UNAVAILABLE")

    def test_sha_invalid_rejected(self):
        d=trusted();d["branch"]["commit"]["sha"]="z"*40
        self.held(self.ready(d),"MAIN_BRANCH_METADATA_INVALID")

    def test_draft_pr_is_never_eligible(self):
        d=trusted();d["pr"]["draft"]=True
        self.held(self.ready(d),"RESEARCH_PR_NOT_READY_FOR_APPROVAL")

    def test_merged_pr_not_equivalent_to_review(self):
        d=trusted();d["pr"]["merged"]=True
        self.held(self.ready(d),"RESEARCH_PR_NOT_READY_FOR_APPROVAL")

    def test_other_repo_pr_number_rejected(self):
        d=trusted();d["pr"]["number"]=999
        self.held(self.ready(d),"RESEARCH_PR_NOT_READY_FOR_APPROVAL")

    def test_only_user_human_other_than_author_counts(self):
        for user in [
            {"login":"repo-owner","type":"User"},
            {"login":"independent-human","type":"Bot"},
            {"login":"independent-human","type":"Organization"},
        ]:
            d=trusted();d["reviews"][0]["user"]=user
            self.held(self.ready(d),"CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING")

    def test_prior_commit_approval_is_stale(self):
        d=trusted();d["reviews"][0]["commit_id"]="d"*40
        self.held(self.ready(d),"CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING")

    def test_latest_review_changes_approval_to_comment(self):
        d=trusted();d["reviews"].append({
            "user":{"login":"independent-human","type":"User"},
            "state":"COMMENTED","commit_id":PR_SHA})
        self.held(self.ready(d),"CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING")

    def test_missing_review_data_fails_closed(self):
        d=trusted();d["reviews"]={"_error":"GITHUB_ADMIN_READ_FORBIDDEN"}
        self.held(self.ready(d),"CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING")

    def test_unauthorized_admin_bypass_is_blocked(self):
        d=trusted();d["protection"]["enforce_admins"]={"enabled":False}
        self.held(self.ready(d),"ADMIN_BYPASS_NOT_BLOCKED")

    def test_no_review_rule_blocks(self):
        d=trusted();d["protection"]["required_pull_request_reviews"]=None
        self.held(self.ready(d),"INDEPENDENT_APPROVAL_NOT_REQUIRED")

    def test_boolean_review_count_not_accepted(self):
        d=trusted();d["protection"]["required_pull_request_reviews"][
            "required_approving_review_count"]=True
        self.held(self.ready(d),"INDEPENDENT_APPROVAL_NOT_REQUIRED")

    def test_hidden_pr_review_bypass_exception_blocks(self):
        for exception in (
            {"users":[{"login":"someone"}],"teams":[],"apps":[]},
            {"users":[],"teams":[],"apps":[{"slug":"foreign"}]},
            {"users":[],"teams":[{"slug":"bypass-team"}],"apps":[]},
            {"users":"not-a-list","teams":[],"apps":[]},
        ):
            d=trusted()
            d["protection"]["required_pull_request_reviews"][
                "bypass_pull_request_allowances"]=exception
            self.held(self.ready(d),
                      "REVIEW_BYPASS_ALLOWANCE_PRESENT_OR_UNREADABLE")

    def test_empty_pr_review_bypass_list_is_not_an_override(self):
        d=trusted()
        d["protection"]["required_pull_request_reviews"][
            "bypass_pull_request_allowances"]={"users":[],"teams":[],"apps":[]}
        r=self.ready(d)
        self.held(r)
        self.assertTrue(r["governance_preflight_requirements_observed"])

    def test_last_other_reviewer_changes_requested_blocks(self):
        d=trusted()
        d["reviews"].append({
            "user":{"login":"second-human","type":"User"},
            "state":"CHANGES_REQUESTED","commit_id":PR_SHA})
        self.held(self.ready(d),
                  "CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING")

    def test_full_review_page_requires_pagination_before_approval(self):
        d=trusted()
        d["reviews"] += [
            {"user":{"login":f"human-{i}","type":"User"},
             "state":"COMMENTED","commit_id":PR_SHA}
            for i in range(99)
        ]
        self.assertEqual(len(d["reviews"]),100)
        self.held(self.ready(d),
                  "CURRENT_HEAD_INDEPENDENT_HUMAN_APPROVAL_MISSING")

    def test_no_stale_approval_dismissal_blocks(self):
        d=trusted();d["protection"]["required_pull_request_reviews"][
            "dismiss_stale_reviews"]=False
        self.held(self.ready(d),"STALE_REVIEWS_NOT_DISMISSED")

    def test_no_last_push_approval_blocks(self):
        d=trusted();d["protection"]["required_pull_request_reviews"][
            "require_last_push_approval"]=False
        self.held(self.ready(d),"LAST_PUSH_APPROVAL_NOT_REQUIRED")

    def test_unprotected_required_ci_blocks(self):
        d=trusted();d["protection"]["required_status_checks"]["strict"]=False
        self.held(self.ready(d),"STRICT_REQUIRED_CI_NOT_ENFORCED")

    def test_legacy_check_contexts_without_app_binding_block(self):
        d=trusted();d["protection"]["required_status_checks"]={
            "strict":True,"contexts":list(REQUIRED)}
        self.held(self.ready(d),"APP_PINNED_CI_NOT_AVAILABLE")

    def test_all_known_checks_required_not_one_green_test(self):
        d=trusted();d["protection"]["required_status_checks"]["checks"]=[
            {"context":"validate","app_id":ACTIONS_APP_ID}]
        self.held(self.ready(d),"MANDATORY_CI_CHECKS_MISSING")

    def test_checks_must_be_bound_to_github_actions_app(self):
        d=trusted()
        d["protection"]["required_status_checks"]["checks"][0]["app_id"]=0
        self.held(self.ready(d),"MANDATORY_CI_NOT_PINNED_TO_GITHUB_ACTIONS")

    def test_conflicting_app_id_duplicate_check_name_blocks(self):
        d=trusted()
        check=d["protection"]["required_status_checks"]["checks"][0]
        d["protection"]["required_status_checks"]["checks"].append({
            "context":check["context"],"app_id":22})
        self.held(self.ready(d),"APP_PINNED_CI_MALFORMED_OR_AMBIGUOUS")

    def test_force_push_and_delete_both_blocked(self):
        for field,expected in [
            ("allow_force_pushes","FORCE_PUSHES_NOT_BLOCKED"),
            ("allow_deletions","BRANCH_DELETION_NOT_BLOCKED"),
        ]:
            d=trusted();d["protection"][field]={"enabled":True}
            self.held(self.ready(d),expected)

    def test_inaccessible_required_protection_cannot_be_bypassed(self):
        d=trusted();d["protection"]={"_error":"GITHUB_ADMIN_READ_FORBIDDEN"}
        self.held(self.ready(d),"PROTECTION_READ_UNAVAILABLE")

    def test_unreviewed_ruleset_bypass_scope_fails_closed(self):
        d=trusted();d["rulesets"]=[{"id":100,"name":"unreviewed"}]
        self.held(self.ready(d),"RULESET_BYPASS_SCOPE_UNREVIEWED")

    def test_signer_workflow_must_exist_on_main(self):
        for failure,reason in [
            ({"_error":"GITHUB_RESOURCE_NOT_FOUND"},
             "APPROVED_MAIN_SIGNER_WORKFLOW_ABSENT"),
            ({"path":"wrong.yml","sha":"c"*40,"type":"file","size":4500},
             "APPROVED_MAIN_SIGNER_WORKFLOW_INVALID"),
        ]:
            d=trusted();d["signer_workflow"]=failure
            self.held(self.ready(d),reason)

    def test_non_manual_or_non_main_context_blocked(self):
        for field,bad in [
            ("GITHUB_EVENT_NAME","pull_request"),
            ("GITHUB_REF","refs/heads/research"),
            ("GITHUB_REPOSITORY","other/repo"),
            ("GITHUB_REPOSITORY_ID","0"),
            ("GITHUB_REF_TYPE","tag"),
        ]:
            d=ctx();d[field]=bad
            self.held(self.ready(context=d),"NOT_AN_APPROVED_MANUAL_MAIN_RUN")

    def test_main_sha_drift_prevents_main_canary(self):
        d=ctx();d["GITHUB_SHA"]="f"*40
        self.held(self.ready(context=d),"MAIN_SHA_DRIFT_OR_UNTRUSTED_SIGNER_RUN")

    def test_incomplete_snapshot_blocks(self):
        d=trusted();del d["protection"]
        self.held(self.ready(d),"GOVERNANCE_EVIDENCE_INCOMPLETE")

    def test_api_reader_get_only_and_single_known_host(self):
        calls=[]
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):
                return b'{"name":"main","protected":false}'
        def fake(req,timeout):
            calls.append((req.full_url,req.get_method(),timeout))
            return Response()
        with patch("ops.original_a_signer_governance_readiness.urlopen",
                   side_effect=fake):
            result=github_reader("synthetic-token")(ENDPOINTS["branch"])
        self.assertEqual(result["protected"],False)
        self.assertEqual(calls,[(
            "https://api.github.com"+ENDPOINTS["branch"],"GET",12)])
        with self.assertRaisesRegex(ReadUnavailable,"UNAPPROVED_GITHUB_API_PATH"):
            github_reader()("/repos/evil/private-data")

    def test_protection_403_is_stable_non_secret_code(self):
        with patch("ops.original_a_signer_governance_readiness.urlopen",
                   side_effect=HTTPError("https://api.github.com",403,
                                         "forbidden",{},io.BytesIO(b"secret"))):
            with self.assertRaisesRegex(ReadUnavailable,"GITHUB_ADMIN_READ_FORBIDDEN"):
                github_reader("synthetic-token")(ENDPOINTS["protection"])

    def test_snapshot_keeps_other_diagnostics_after_403(self):
        def get(path):
            if path==ENDPOINTS["protection"]:
                raise ReadUnavailable("GITHUB_ADMIN_READ_FORBIDDEN")
            return trusted()[next(k for k,v in ENDPOINTS.items() if v==path)]
        data=snapshot(get)
        self.assertEqual(data["protection"]["_error"],"GITHUB_ADMIN_READ_FORBIDDEN")
        self.assertEqual(len(data),len(ENDPOINTS))

    def test_cli_has_only_readonly_and_never_exits_as_signer_success(self):
        d=trusted();d["branch"]["protected"]=False
        with patch("ops.original_a_signer_governance_readiness.snapshot",
                   return_value=d), patch(
                   "ops.original_a_signer_governance_readiness.github_reader"):
            self.assertEqual(main(["--live-readonly","--require-hold"]),0)
            self.assertEqual(main(["--live-readonly"]),1)


if __name__=="__main__":
    unittest.main()
