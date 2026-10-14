import unittest
from shadow_mobile_report import render

class MobileReportTests(unittest.TestCase):
    def inputs(self):
        return (
            {"status":"HOLD","production_recommendations":"DISABLED","valid_scored_fixtures":0,
             "target":1000,"matured_awaiting_ft":9,"source_stale_14d":True,
             "blocking_reasons":["NO_VERIFIED_PREDICTION_RESULT_PAIRS"],
             "research_queue":[{"home":"A","away":"B","kickoff_utc":"2026-10-10T12:00:00Z"} for _ in range(9)]},
            {"status":"PASS","production_recommendations":"DISABLED"},
            {"status":"SHADOW_ONLY","production_recommendations":"DISABLED","valid_fixtures":0},
            {"status":"HOLD","production_recommendations":"DISABLED","sources":[
                {"provider":"OpenLigaDB","records":[{"score_ft":[1,0]}]}]})
    def test_phone_report_displays_real_blockers(self):
        report=render(*self.inputs())
        self.assertIn("0/1000",report)
        self.assertIn("NO_VERIFIED_PREDICTION_RESULT_PAIRS",report)
        self.assertIn("OpenLigaDB | 1",report)
        self.assertIn("無完場記錄",report)
        self.assertIn("A 對 B｜待獨立核實",report)
        self.assertIn("\n## 未解決阻礙\n",report)
    def test_rejects_mismatched_research_queue(self):
        items=list(self.inputs())
        items[0]["research_queue"]=[]
        with self.assertRaisesRegex(ValueError,"RESEARCH_QUEUE_MISMATCH"):
            render(*items)
    def test_rejects_enabled_production(self):
        items=list(self.inputs())
        items[2]["production_recommendations"]="ENABLED"
        with self.assertRaisesRegex(ValueError,"PRODUCTION_FLAG_UNSAFE"):
            render(*items)
    def test_rejects_inconsistent_count(self):
        items=list(self.inputs())
        items[2]["valid_fixtures"]=1
        with self.assertRaisesRegex(ValueError,"SAMPLE_COUNTER_MISMATCH"):
            render(*items)
    def test_rejects_failed_integrity(self):
        items=list(self.inputs())
        items[1]["status"]="FAIL"
        with self.assertRaisesRegex(ValueError,"INTEGRITY_NOT_CONFIRMED"):
            render(*items)

if __name__=="__main__":
    unittest.main()
