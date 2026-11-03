"""Fail-closed mobile control tower V8 bootstrap/source-binding regressions.

Static tests run offline; they do not assert browser or deployment readiness.
"""
from pathlib import Path
import unittest

PAGE = Path(__file__).resolve().parents[2] / "docs" / "control-tower-mobile" / "index.html"


class MobileControlTowerV8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = PAGE.read_text(encoding="utf-8")

    def test_initial_dashboard_never_claims_stale_ci_or_protection(self):
        self.assertIn('id="kpi-ci" class="kpi-val warn">未核實', self.html)
        self.assertIn('id="github-ci-count">未核實', self.html)
        self.assertIn("main:{sha:null,protected:null,checked_at_utc:null}", self.html)
        self.assertIn("ci:{number:CI_TARGET_PR,head:null,passed:null,total:null,status:'UNVERIFIED',checked_at_utc:null}", self.html)
        self.assertNotIn("main:{sha:'b8fdb45", self.html)

    def test_live_ci_binds_exact_mobile_pr_head(self):
        self.assertIn("const prTarget=S.pr.find(x=>x.number===CI_TARGET_PR)", self.html)
        self.assertIn("c.head_sha===sha", self.html)
        self.assertIn("checksReadyForCurrentHead(check.value,prTarget?.head)", self.html)
        self.assertIn("S.ci={number:CI_TARGET_PR,head:prTarget.head", self.html)
        self.assertIn("S.ci={number:CI_TARGET_PR,head:prTarget?.head||null", self.html)
        self.assertIn("const CI_TARGET_PR=427", self.html)
        self.assertNotIn("const pr412=S.pr.find", self.html)

    def test_site_self_report_needs_current_session_main_read(self):
        self.assertIn("typeof S.main.checked_at_utc==='string'", self.html)
        self.assertIn("Number.isFinite(Date.parse(S.main.checked_at_utc))", self.html)
        self.assertIn("typeof S.main.sha==='string'", self.html)
        self.assertIn("status.source_commit_sha===S.main.sha", self.html)
        self.assertIn("S.site={status:'HOLD'", self.html)

    def test_release_rails_and_research_coverage_remain(self):
        for token in ("release_authorized:false", "deploy_allowed:false",
                      "live_execution_allowed:false",
                      "production_recommendations:'DISABLED'",
                      "number:405,title", "number:409,title",
                      "number:412,title", "number:416,title"):
            with self.subTest(token=token):
                self.assertIn(token, self.html)
        self.assertNotIn("Authorization: 'Bearer", self.html)


if __name__ == "__main__":
    unittest.main()
