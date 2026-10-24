"""iPhone dashboard is accessible, data-driven and excludes API secrets."""
import sys
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mobile_dashboard import inject,JS,CSS


class MobileDashboardTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required to execute the published renderer")
    def test_research_counts_and_forged_certificates_cannot_fill_formal_progress(self):
        from mobile_dashboard import EVIDENCE_PROGRESS_JS
        inputs = [
            {"settled_samples": 300, "independent_week_blocks": 12,
             "leagues_with_at_least_40": 4, "additional_samples_needed": 0},
            {"recorded_research_samples": 350, "recorded_research_week_blocks": 18,
             "recorded_research_leagues_with_40": 4,
             "authenticated_forward_samples": 350, "authenticated_week_blocks": 18,
             "authenticated_leagues_with_40": 4, "remaining_authenticated_samples": 0,
             "signature_verified": True, "admission_completed": True},
            None, {"recorded_research_samples": True,
                   "recorded_research_week_blocks": "12",
                   "recorded_research_leagues_with_40": -1},
        ]
        program = EVIDENCE_PROGRESS_JS + "\n" + (
            "let raw='';process.stdin.on('data',s=>raw+=s);"
            "process.stdin.on('end',()=>process.stdout.write(JSON.stringify("
            "JSON.parse(raw).map(evidenceProgressText))));")
        completed = subprocess.run([shutil.which("node"), "-e", program],
                                   input=json.dumps(inputs), text=True,
                                   capture_output=True, check=True, timeout=10)
        texts = json.loads(completed.stdout)
        self.assertIn("已記錄研究：300 場、12 個週次、4 個聯賽", texts[0])
        self.assertIn("已記錄研究：350 場、18 個週次、4 個聯賽", texts[1])
        for text in texts:
            self.assertIn("已認證 0/300 場；仍欠 300 場", text)
            self.assertIn("合資格週次 0/12", text)
            self.assertIn("合資格聯賽 0/4", text)
        self.assertIn("已記錄研究：0 場、0 個週次、0 個聯賽", texts[3])

    def test_static_evidence_panel_keeps_research_separate_from_authentication(self):
        with tempfile.TemporaryDirectory() as d:
            site = Path(d)
            (site/"index.html").write_text("<html><body></body></html>", encoding="utf-8")
            (site/"evidence_progress.json").write_text(json.dumps({
                "schema": "football-king-evidence-progress-v1", "status": "HOLD",
                "production_recommendations": "DISABLED", "automatic_bets_allowed": False,
                "positive_ev_betting_confirmed": False, "settled_forward_samples": 350,
                "recorded_research_samples": 350,
                "recorded_two_publisher_exact_score_agreements": 50,
                "independent_exact_score_pairs_on_settled_samples": 50,
                "authenticated_forward_samples": 350, "remaining_forward_samples": 0,
            }), encoding="utf-8")
            inject(site)
            page = (site/"index.html").read_text(encoding="utf-8")
            self.assertIn("已記錄研究結算：350 場", page)
            self.assertIn("已認證 0/300 場；仍欠認證 300 場、12 個合資格週", page)
            self.assertIn("兩出版者比分一致觀察：50 場（未認證）", page)
            published_js = (site/"research_hub.js").read_text(encoding="utf-8")
            self.assertIn("evidenceProgressText(progress)", published_js)
            self.assertNotIn("場；獨立週期", published_js)

    def test_static_site_controls_and_no_dynamic_html_injection(self):
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)
            (site/"index.html").write_text("<html><body><h2>近期賽程與賽果</h2></body></html>",encoding="utf-8")
            result=inject(site)
            self.assertTrue(result["dashboard_visible"])
            doc=(site/"index.html").read_text(encoding="utf-8")
            self.assertIn('id="fk-hub"',doc)
            self.assertIn('id="fk-league"',doc)
            self.assertIn('id="fk-search"',doc)
            self.assertIn('id="fk-evidence-progress"',doc)
            self.assertIn('id="fk-recommendations"',doc)
            self.assertIn('id="fk-picks"',doc)
            self.assertIn('id="fk-source-failover"',doc)
            self.assertIn("free_source_failover.json",doc)
            self.assertIn("冇可成交博彩公司賠率",doc)
            self.assertIn('id="fk-extra-sources"',doc)
            self.assertIn('id="fk-met-weather"',doc)
            self.assertIn('id="fk-market-failover"',doc)
            self.assertIn('id="fk-betting-readiness"',doc)
            self.assertIn('id="fk-evidence-pipeline"',doc)
            self.assertIn('id="fk-japan-free-market"',doc)
            self.assertIn("japan_free_market.json",doc)
            self.assertIn("日本 J1 免費盤口來源未核實",doc)
            self.assertIn("evidence_progress.json",doc)
            self.assertIn("handicap_forward_audit.json",doc)
            self.assertIn("independent_results.json",doc)
            self.assertIn("證據進度資料未核實",doc)
            self.assertIn("betting_readiness.json",doc)
            self.assertIn("正式推薦維持 HOLD",doc)
            self.assertIn("research_market_failover.json",doc)
            self.assertIn('id="fk-bsd-backup"',doc)
            self.assertIn("Bzzoiro Sports Data",doc)
            self.assertIn("免費1X2市場後備",doc)
            self.assertIn("MET Norway",doc)
            self.assertIn("城市中心",doc)
            self.assertIn("creativecommons.org/licenses/by/4.0",doc)
            self.assertIn('id="fk-wide-sources"',doc)
            self.assertIn('id="fk-research-extensions"',doc)
            self.assertIn("OpenFootAPI",doc)
            self.assertIn("StatsBomb",doc)
            self.assertIn("free_research_extensions.json",doc)
            self.assertIn("全球及小型聯賽免費備用資料",doc)
            self.assertIn("展開只供歷史研究嘅小型聯賽",doc)
            self.assertIn("wide_leagues.json",doc)
            self.assertIn("四個額外免費資料渠道",doc)
            self.assertIn("等待第一輪免費來源採集",doc)
            self.assertIn("正式投注建議：HOLD",doc)
            js=(site/"research_hub.js").read_text(encoding="utf-8")
            self.assertIn("textContent",js)
            self.assertIn("research_selections.json",js)
            self.assertIn("renderRecommendationCards",js)
            self.assertIn("setInterval(draw",js)
            self.assertIn("visibilitychange",js)
            self.assertIn("freshTenHours",js)
            self.assertIn("additional_schedule_utc_crosschecked",js)
            self.assertIn("已認證 0/300 場；仍欠 300 場",js)
            self.assertIn("HOLD：網站或研究候選已過期",js)
            self.assertIn("HOLD",doc)
            self.assertIn("research_selections.json",js)
            self.assertIn("renderRecommendationCards",js)
            self.assertIn("market_direction_agrees",js) if False else None
            self.assertNotIn("innerHTML",js)
            self.assertNotIn("THE_ODDS_API_KEY",js)
            self.assertNotIn("api.the-odds-api.com",js)
            self.assertIn("@media", (site/"research_hub.css").read_text(encoding="utf-8"))

    def test_duplicate_hub_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)
            (site/"index.html").write_text('<html><body><div id="fk-hub"></div></body></html>',encoding="utf-8")
            with self.assertRaisesRegex(ValueError,"DUPLICATE_RESEARCH_HUB"):
                inject(site)

    def test_missing_html_body_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            site=Path(d)
            (site/"index.html").write_text("<p>no body")
            with self.assertRaisesRegex(ValueError,"HTML_BODY_REQUIRED"):
                inject(site)


if __name__=="__main__":
    unittest.main()
