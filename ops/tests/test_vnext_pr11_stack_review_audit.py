"""PR-11 synthetic-only premerge review/CI inventory security tests."""
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vnext_pr11_stack_review_audit import (
    APP_ID, COMMON, FINAL, PREFIX, STAGES, inspect_premerge_stack,
    github_reader, main,
)


def snapshot():
    branch = {"name": "main", "protected": True, "commit": {"sha": "a" * 40}}
    policy = {
        "required_pull_request_reviews": {
            "required_approving_review_count": 1,
            "dismiss_stale_reviews": True,
            "require_last_push_approval": True,
        },
        "enforce_admins": {"enabled": True},
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": name, "app_id": APP_ID} for name in sorted(FINAL)],
        },
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
    }
    out = {
        PREFIX + "/branches/main": branch,
        PREFIX + "/branches/main/protection": policy,
    }
    out[PREFIX + "/pulls/432"] = {
        "number": 432, "merged_at": None, "state": "open",
        "head": {"ref": "research/unified-score-matrix-vnext-20261104"},
    }
    for n, headbranch, basebranch in STAGES:
        sha = "%040x" % n
        path = PREFIX + f"/pulls/{n}"
        out[path] = {
            "number": n, "state": "open", "draft": False,
            "merged_at": None, "user": {"login": "synthetic-author", "type": "User"},
            "head": {
                "ref": headbranch, "sha": sha,
                "repo": {"full_name": "CHANCHUNWA1989/football-king-report"},
            },
            "base": {
                "ref": basebranch,
                "repo": {"full_name": "CHANCHUNWA1989/football-king-report"},
            },
        }
        out[path + "/reviews?per_page=100"] = [{
            "id": n, "user": {"login": "other-human-account", "type": "User"},
            "submitted_at": "2026-11-04T11:00:00Z", "state": "APPROVED",
            "commit_id": sha,
        }]
        required = FINAL if n == 440 else COMMON
        checks = [{
            "name": label, "head_sha": sha, "status": "completed",
            "conclusion": "success", "app": {"id": APP_ID},
        } for label in sorted(required)]
        if n != 440:
            # Old legacy duplicate 'regression' exists but is intentionally
            # NOT a mandatory identity before the PR-10 rename.
            checks += [
                {"name": "regression", "head_sha": sha,
                 "status": "completed", "conclusion": "success", "app": {"id": APP_ID}},
                {"name": "regression", "head_sha": sha,
                 "status": "completed", "conclusion": "success", "app": {"id": APP_ID}},
            ]
        out[PREFIX + f"/commits/{sha}/check-runs?per_page=100"] = {
            "total_count": len(checks), "check_runs": checks,
        }
    return out


def evaluate(data=None):
    entries = snapshot() if data is None else data
    return inspect_premerge_stack(lambda path: entries[path])


def codes(report):
    return {(x["code"], x.get("pr")) for x in report["blockers"]}


class Pr11EvidenceTests(unittest.TestCase):
    def test_synthetic_complete_inventory_never_authorizes_merging(self):
        result = evaluate()
        self.assertEqual(result["status"], "RESEARCH_REVIEW_CHECKS_OBSERVED_ONLY")
        self.assertEqual(result["expected_stack_count"], 10)
        self.assertEqual(len(result["observed"]), 10)
        self.assertEqual(result["blockers"], [])
        for key in ("github_human_identity_independently_established",
                    "independent_security_review_verified", "permission_to_merge",
                    "external_signature_verified", "real_data_licence_verified",
                    "model_accuracy_improvement_verified", "positive_ev_verified"):
            self.assertFalse(result[key])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_actual_unprotected_branch_must_hold(self):
        data = snapshot()
        data[PREFIX + "/branches/main"]["protected"] = False
        self.assertIn(("MAIN_NOT_PROTECTED", None), codes(evaluate(data)))

    def test_api_403_does_not_assume_review_policy(self):
        data = snapshot()
        del data[PREFIX + "/branches/main/protection"]
        self.assertIn(("DETAILED_PROTECTION_API_UNAVAILABLE", None), codes(evaluate(data)))

    def test_any_one_draft_pr_makes_full_stack_hold(self):
        for n in (429, 436, 440):
            with self.subTest(n=n):
                data = snapshot()
                data[PREFIX + f"/pulls/{n}"]["draft"] = True
                r = evaluate(data)
                self.assertEqual(r["status"], "HOLD")
                self.assertIn(("PR_DRAFT_NOT_REVIEW_READY", n), codes(r))

    def test_wrong_base_or_head_branch_rejected(self):
        for key, value in (("base", "main"), ("head", "malicious-branch")):
            with self.subTest(key=key):
                data = snapshot()
                pr = data[PREFIX + "/pulls/440"]
                pr[key]["ref"] = value
                self.assertIn(("PR_STACK_BASE_OR_HEAD_MISMATCH", 440),
                              codes(evaluate(data)))

    def test_alternative_pr432_not_silently_included(self):
        self.assertNotIn(432, [n for n, _, _ in STAGES])
        self.assertEqual([n for n, _, _ in STAGES],
                         [429, 430, 431, 433, 434, 435, 436, 437, 438, 440])

    def test_no_review_or_author_review_does_not_approve(self):
        for value in ([], [{
            "id": 9, "user": {"login": "synthetic-author", "type": "User"},
            "submitted_at": "2026-11-04T11:00:00Z", "state": "APPROVED",
            "commit_id": "%040x" % 438,
        }]):
            with self.subTest(value=value):
                data = snapshot()
                data[PREFIX + "/pulls/438/reviews?per_page=100"] = value
                self.assertIn(("EXACT_HEAD_INDEPENDENT_APPROVAL_MISSING", 438),
                              codes(evaluate(data)))

    def test_stale_approval_on_previous_sha_does_not_count(self):
        data = snapshot()
        data[PREFIX + "/pulls/429/reviews?per_page=100"][0]["commit_id"] = "f" * 40
        self.assertIn(("EXACT_HEAD_INDEPENDENT_APPROVAL_MISSING", 429),
                      codes(evaluate(data)))

    def test_last_review_changes_requested_overrides_earlier_approval(self):
        data = snapshot()
        items = data[PREFIX + "/pulls/440/reviews?per_page=100"]
        items.append({
            "id": 999, "user": {"login": "other-human-account", "type": "User"},
            "submitted_at": "2026-11-04T12:00:00Z",
            "state": "CHANGES_REQUESTED", "commit_id": "%040x" % 440,
        })
        self.assertIn(("EXACT_HEAD_INDEPENDENT_APPROVAL_MISSING", 440),
                      codes(evaluate(data)))

    def test_another_reviewer_requesting_changes_blocks_approval(self):
        data = snapshot()
        data[PREFIX + "/pulls/436/reviews?per_page=100"].append({
            "id": 1001,
            "user": {"login": "different-independent-account", "type": "User"},
            "submitted_at": "2026-11-04T12:00:00Z",
            "state": "CHANGES_REQUESTED", "commit_id": "%040x" % 436,
        })
        self.assertIn(("EXACT_HEAD_INDEPENDENT_APPROVAL_MISSING", 436),
                      codes(evaluate(data)))

    def test_merged_alternative_pr03_is_a_hard_blocker(self):
        data = snapshot()
        data[PREFIX + "/pulls/432"]["merged_at"] = "2026-11-04T12:00:00Z"
        self.assertIn(("ALTERNATIVE_PR03_ALREADY_MERGED", None), codes(evaluate(data)))

    def test_unreadable_alternative_pr03_is_a_hard_blocker(self):
        data = snapshot()
        del data[PREFIX + "/pulls/432"]
        self.assertIn(("ALTERNATIVE_PR_STATUS_UNAVAILABLE", None),
                      codes(evaluate(data)))

    def test_bot_review_does_not_pass(self):
        data = snapshot()
        data[PREFIX + "/pulls/431/reviews?per_page=100"][0]["user"]["type"] = "Bot"
        self.assertIn(("EXACT_HEAD_INDEPENDENT_APPROVAL_MISSING", 431),
                      codes(evaluate(data)))

    def test_malformed_or_truncated_reviews_fail_closed(self):
        data = snapshot()
        data[PREFIX + "/pulls/435/reviews?per_page=100"] = ["untrusted"] * 100
        self.assertIn(("EXACT_HEAD_INDEPENDENT_APPROVAL_MISSING", 435),
                      codes(evaluate(data)))

    def test_missing_app_or_failed_check_blocks(self):
        for value in (0, "15368", 123):
            with self.subTest(app_id=value):
                data = snapshot()
                checks = data[PREFIX + "/commits/" + ("%040x" % 440) + "/check-runs?per_page=100"]["check_runs"]
                checks[0]["app"]["id"] = value
                self.assertIn(("EXACT_HEAD_REQUIRED_CI_NOT_VERIFIED", 440),
                              codes(evaluate(data)))
        data = snapshot()
        checks = data[PREFIX + "/commits/" + ("%040x" % 429) + "/check-runs?per_page=100"]["check_runs"]
        checks[0]["conclusion"] = "failure"
        self.assertIn(("EXACT_HEAD_REQUIRED_CI_NOT_VERIFIED", 429),
                      codes(evaluate(data)))

    def test_legacy_duplicate_regression_is_not_pinned_security_check(self):
        data = snapshot()
        path = PREFIX + "/commits/" + ("%040x" % 440) + "/check-runs?per_page=100"
        rows = data[path]["check_runs"]
        rows[:] = [r for r in rows if r["name"] != "security-regression"]
        rows.append({"name": "regression", "head_sha": "%040x" % 440,
                     "status": "completed", "conclusion": "success",
                     "app": {"id": APP_ID}})
        self.assertIn(("EXACT_HEAD_REQUIRED_CI_NOT_VERIFIED", 440),
                      codes(evaluate(data)))

    def test_duplicate_mandatory_check_blocks_even_both_success(self):
        data = snapshot()
        path = PREFIX + "/commits/" + ("%040x" % 440) + "/check-runs?per_page=100"
        rows = data[path]["check_runs"]
        rows.append(copy.deepcopy(rows[0]))
        data[path]["total_count"] = len(rows)
        self.assertIn(("EXACT_HEAD_REQUIRED_CI_NOT_VERIFIED", 440),
                      codes(evaluate(data)))

    def test_incomplete_check_runs_api_page_blocks(self):
        data = snapshot()
        path = PREFIX + "/commits/" + ("%040x" % 437) + "/check-runs?per_page=100"
        data[path]["total_count"] += 1
        self.assertIn(("EXACT_HEAD_REQUIRED_CI_NOT_VERIFIED", 437),
                      codes(evaluate(data)))

    def test_check_attached_to_old_sha_does_not_count(self):
        data = snapshot()
        path = PREFIX + "/commits/" + ("%040x" % 440) + "/check-runs?per_page=100"
        data[path]["check_runs"][0]["head_sha"] = "f" * 40
        self.assertIn(("EXACT_HEAD_REQUIRED_CI_NOT_VERIFIED", 440),
                      codes(evaluate(data)))

    def test_branch_policy_requires_reviews_and_all_six_pinned_checks(self):
        data = snapshot()
        policy = data[PREFIX + "/branches/main/protection"]
        policy["required_pull_request_reviews"]["required_approving_review_count"] = 0
        self.assertIn(("INDEPENDENT_FRESH_REVIEWS_NOT_ENFORCED", None),
                      codes(evaluate(data)))
        data = snapshot()
        policy = data[PREFIX + "/branches/main/protection"]
        policy["required_status_checks"]["checks"].pop()
        self.assertIn(("SIX_MANDATORY_CI_CHECKS_NOT_APP_PINNED", None),
                      codes(evaluate(data)))

    def test_changed_pr_head_between_read_and_check_fails(self):
        data = snapshot()
        path = PREFIX + "/pulls/440"
        times = {"count": 0}
        def fetch(key):
            if key == path:
                times["count"] += 1
                if times["count"] == 2:
                    changed = copy.deepcopy(data[key])
                    changed["head"]["sha"] = "f" * 40
                    return changed
            return data[key]
        self.assertIn(("PR_HEAD_MOVED_DURING_AUDIT", 440),
                      codes(inspect_premerge_stack(fetch)))

    def test_missing_pr_or_review_endpoint_never_silently_skip(self):
        for path, expected in [
            (PREFIX + "/pulls/440", "PR_METADATA_UNAVAILABLE"),
            (PREFIX + "/pulls/440/reviews?per_page=100", "PR_REVIEWS_UNAVAILABLE"),
        ]:
            with self.subTest(path=path):
                data = snapshot()
                del data[path]
                self.assertIn((expected, 440), codes(evaluate(data)))

    def test_cli_always_nonzero_even_with_synthetic_success(self):
        with patch("vnext_pr11_stack_review_audit.github_reader",
                   return_value=lambda key: snapshot()[key]):
            with patch("vnext_pr11_stack_review_audit.os.environ.get",
                       return_value="synthetic-token"):
                self.assertEqual(main(), 1)

    def test_no_token_cannot_open_reader(self):
        with self.assertRaisesRegex(ValueError, "READ_ONLY_GITHUB_TOKEN_UNAVAILABLE"):
            github_reader("")


if __name__ == "__main__":
    unittest.main()
