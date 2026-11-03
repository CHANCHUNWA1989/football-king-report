"""V10 mobile view: current mobile PR CI, dynamic source count and HOLD gates.

Offline markup regression only; a real Safari session and server deployment
remain separate validation requirements.
"""
from pathlib import Path
import unittest

PAGE = Path(__file__).resolve().parents[2] / "docs/control-tower-mobile/index.html"


class MobileControlTowerV10Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = PAGE.read_text(encoding="utf-8")

    def test_current_mobile_pr_is_checked_by_exact_head(self):
        p = self.page
        self.assertIn("const CI_TARGET_PR=427", p)
        self.assertIn("const prTarget=S.pr.find(x=>x.number===CI_TARGET_PR)", p)
        self.assertIn("checksReadyForCurrentHead(check.value,prTarget?.head)", p)
        self.assertIn("c.head_sha!==sha", p)
        self.assertIn("S.ci={number:CI_TARGET_PR,head:prTarget.head", p)
        self.assertIn("S.ci={number:CI_TARGET_PR,head:prTarget?.head||null", p)
        self.assertNotIn("const pr416=S.pr.find", p)

    def test_v8_v9_prs_present_and_initial_review_unknown(self):
        p = self.page
        self.assertIn("number:421,title:'V8", p)
        self.assertIn("number:422,title:'V9", p)
        self.assertIn("number:424,title:'V10", p)
        self.assertIn("ci:{number:CI_TARGET_PR,head:null,passed:null,total:null,status:'UNVERIFIED'", p)
        self.assertIn("reviews:null,review_verified_at:null", p)
        self.assertNotIn("reviews:0,review_verified_at:SNAPSHOT_AT", p)

    def test_source_count_derived_from_tracked_prs(self):
        p = self.page
        self.assertIn("const expected=3+S.pr.length;if(success<expected)", p)
        self.assertIn("success+'/'+expected+' 組公開資料", p)
        self.assertNotIn("success+'/7 組公開資料", p)

    def test_safe_export_and_release_hold_remain(self):
        p = self.page
        self.assertIn("ai-control-tower-mobile-v11-snapshot.json", p)
        for token in ("release_authorized:false", "deploy_allowed:false",
                      "live_execution_allowed:false",
                      "production_recommendations:'DISABLED'",
                      "S.site={status:'HOLD'"):
            with self.subTest(token=token):
                self.assertIn(token, p)
        self.assertNotIn("Authorization: 'Bearer", p)


if __name__ == "__main__":
    unittest.main()
