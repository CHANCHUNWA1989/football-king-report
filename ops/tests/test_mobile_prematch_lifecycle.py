"""Regression: a still-fresh research report must not show an already-started match.

This tests the exact JavaScript shipped to the iPhone page. It is not a live
odds validation, calibrated forecast, or authorization for betting.
"""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mobile_dashboard import JS, inject


class PrematchLifecycleGuardTests(unittest.TestCase):
    def test_all_three_research_lists_use_per_fixture_live_clock_guard(self):
        self.assertIn("function isPendingPrematch(p, nowMs=Date.now())", JS)
        self.assertIn("const eligible=p=>fits(p)&&isPendingPrematch(p);", JS)
        # All three surfaces: paired research, review and model-only fallback.
        self.assertEqual(JS.count(".filter(eligible)"), 3)
        self.assertIn("已開賽或距離開波不足60分鐘", JS)
        self.assertIn("setInterval(draw, 60*1000)", JS)
        self.assertIn("document.addEventListener('visibilitychange',draw)", JS)
        self.assertIn("正式投注建議：HOLD", Path(__file__).resolve().parents[1]
                      .joinpath("mobile_dashboard.py").read_text(encoding="utf-8"))

    @unittest.skipUnless(shutil.which("node"), "Node is needed to execute shipped JS")
    def test_actual_browser_helper_rejects_started_near_kickoff_and_bad_time(self):
        start = JS.index("function isPendingPrematch(")
        end = JS.index("function renderRecommendationCards(", start)
        helper = JS[start:end]
        js = helper + """
const now=Date.parse('2026-11-01T16:30:00Z');
const match=utc=>({kickoff_utc:utc});
const cases=[
  match('2026-11-01T17:31:00Z'),       // +61 min
  match('2026-11-01T17:30:00Z'),       // +60: not safe
  match('2026-11-01T17:00:00Z'),       // +30: stale pre-match pick
  match('2026-11-01T16:29:00Z'),       // live/already started
  match('2026-11-01T16:30:00Z'),       // exact kickoff
  match('2026-11-01T17:31:00'),        // timezone missing
  match('not-a-time'),                 // invalid date
  match('2026-11-09T16:30:00Z'),       // outside 7-day window
  match('2026-11-02T01:31:00+08:00'),  // same +61 min with HK offset
  null, {}, {kickoff_utc:true}
];
process.stdout.write(JSON.stringify(cases.map(x=>isPendingPrematch(x,now))));
"""
        result = subprocess.run([shutil.which("node"), "-e", js], text=True,
                                capture_output=True, check=True, timeout=10)
        self.assertEqual(json.loads(result.stdout),
                         [True, False, False, False, False, False, False,
                          False, True, False, False, False])

    def test_published_html_cannot_call_stale_prematch_direction_a_live_tip(self):
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "index.html").write_text(
                "<html><body><h2>近期賽程與賽果</h2></body></html>",
                encoding="utf-8")
            inject(root)
            html = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("未開賽研究觀察", html)
            self.assertIn("非即場主推", html)
            self.assertNotIn("今日研究首選｜", html)
            script = (root / "research_hub.js").read_text(encoding="utf-8")
            self.assertIn("function isPendingPrematch(", script)
            self.assertIn("只供研究", script)


if __name__ == "__main__":
    unittest.main()
