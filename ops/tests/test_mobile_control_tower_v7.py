"""Static safety and structure regression checks for V7 mobile HTML.

This is a no-network, no-Playwright CI check; real browser interactions
are separately exercised with a local mobile viewport test.
"""
from pathlib import Path
import re
import unittest

PATH = Path(__file__).resolve().parents[2] / "docs" / "control-tower-mobile" / "index.html"


class MobileControlTowerV7Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.markup = PATH.read_text(encoding="utf-8")

    def test_self_contained_html_and_mobile_viewport(self):
        self.assertTrue(self.markup.startswith("<!doctype html>"))
        self.assertIn('name="viewport"', self.markup)
        self.assertNotRegex(self.markup, r'<script[^>]+src=')
        self.assertNotRegex(self.markup, r'<link[^>]+rel="stylesheet"')

    def test_all_five_functional_tabs_exist(self):
        for name in ("overview", "modules", "github", "risk", "settings"):
            with self.subTest(name=name):
                self.assertIn('id="view-' + name + '"', self.markup)
                self.assertIn('data-view="' + name + '"', self.markup)
        self.assertIn("function show(which)", self.markup)

    def test_four_research_modules_not_betting_services(self):
        for name in ("football", "kpl", "basketball", "quant"):
            self.assertIn('data-module="' + name + '"', self.markup)
        self.assertIn("live_execution_allowed:false", self.markup)
        self.assertIn("production_recommendations:'DISABLED'", self.markup)
        self.assertIn("release_authorized:false", self.markup)

    def test_no_private_repo_auto_fetch_or_secrets(self):
        self.assertIn("async function syncGitHub()", self.markup)
        self.assertIn("const BASE='https://api.github.com/repos/'+REPO", self.markup)
        self.assertIn("const SITE='https://chanchunwa1989.github.io/football-king-report'", self.markup)
        self.assertNotIn("Authorization: 'Bearer", self.markup)
        self.assertNotRegex(self.markup, r"(?i)fetch\([^;]*(?:global-basketball-ai|global-quant-ai)")
        self.assertNotIn("POST", self.markup)
        self.assertNotIn("PUT", self.markup)
        self.assertNotIn("PATCH", self.markup)

    def test_uncertainty_and_safe_website_release(self):
        self.assertIn("UNVERIFIED", self.markup)
        self.assertIn("未核實", self.markup)
        self.assertIn("HOLD", self.markup)
        self.assertIn("source_commit_sha", self.markup)
        self.assertIn("verified_commit", self.markup)
        self.assertIn("待核", self.markup)
        self.assertIn("非同時來源", self.markup)

    def test_known_prs_named_accurately(self):
        for n in (405, 409, 412, 416):
            self.assertRegex(self.markup, rf"number:{n},title:")
        self.assertIn("V3｜只讀監察", self.markup)
        self.assertIn("V5｜獨立審核", self.markup)
        self.assertIn("V6｜公開網站回讀", self.markup)\n        self.assertIn("V7｜真正可操作嘅手機互動控制塔", self.markup)


if __name__ == "__main__":
    unittest.main()
