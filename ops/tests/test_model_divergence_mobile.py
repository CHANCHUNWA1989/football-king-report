import unittest
from ops.model_divergence_mobile import summarize, render, MAX_FIXTURES
from ops.tests import test_model_divergence_evidence as evidence_tests


class MobileTests(unittest.TestCase):
    def setUp(self):
        case = evidence_tests.EvidenceTests()
        case.setUp()
        self.report = case.call()

    def test_real_adapter_shape(self):
        s = summarize(self.report)
        self.assertTrue(s["input_report_valid"])
        self.assertEqual(s["reported_count"], 1)
        self.assertEqual(s["counts"], {"NO_LARGE_DISAGREEMENT": 1})
        self.assertEqual(s["status"], "HOLD")

    def test_mobile_markup(self):
        html = render(self.report)
        for phrase in ("viewport", "HOLD／DISABLED", "離線報告", "未觸發分歧閾值：1", "Content-Security-Policy"):
            self.assertIn(phrase, html)
        self.assertNotIn("<script", html)

    def test_missing_report(self):
        for value in (None, [], {}, "not a report"):
            self.assertFalse(summarize(value)["input_report_valid"])
            self.assertIn("未有合格報告", render(value))

    def test_flags_cannot_promote(self):
        for field in ("can_recommend_bets", "source_authenticated", "model_calibrated",
                      "source_bytes_verified", "model_input_derivation_verified", "native_identity_authenticated"):
            self.assertFalse(summarize(dict(self.report, **{field:True}))["input_report_valid"])
        self.assertFalse(summarize(dict(self.report, production_recommendations="ENABLED"))["input_report_valid"])

    def test_wrong_totals(self):
        for count in (True, 2, -1, 1.0):
            self.assertFalse(summarize(dict(self.report, counts={"NO_LARGE_DISAGREEMENT":count}))["input_report_valid"])

    def test_invalid_rows(self):
        for patch in ({"manifest_index":True}, {"manifest_index":4}, {"max_gap":float("nan")},
                      {"max_gap":0.2}, {"status":"HOLD"}, {"reason":"UNKNOWN"}):
            row = dict(self.report["results"][0], **patch)
            self.assertFalse(summarize(dict(self.report, results=[row]))["input_report_valid"])

    def test_bounded(self):
        self.assertFalse(summarize(dict(self.report, results=[{}]*(MAX_FIXTURES+1)))["input_report_valid"])

    def test_untrusted_text_not_rendered(self):
        payload = "<script>PRIVATE_PAYLOAD</script>"
        row = dict(self.report["results"][0], secret=payload)
        html = render(dict(self.report, secret=payload, results=[row]))
        self.assertNotIn(payload, html)
        self.assertNotIn("PRIVATE_PAYLOAD", html)

    def test_conflict_warning(self):
        row = dict(self.report["results"][0], status="HOLD", reason="DIRECTION_CONFLICT", max_gap=0.14)
        report = dict(self.report, results=[row], counts={"DIRECTION_CONFLICT":1}, status="HOLD", reason="PAIR_HOLD")
        self.assertTrue(summarize(report)["input_report_valid"])
        self.assertIn("模型預測方向衝突：1", render(report))

    def test_missing_hash_match(self):
        self.assertFalse(summarize(dict(self.report, normalized_documents_hash_match=False))["input_report_valid"])

    def test_inconsistent_aggregate(self):
        self.assertFalse(summarize(dict(self.report, status="HOLD"))["input_report_valid"])
        self.assertFalse(summarize(dict(self.report, reason="PAIR_HOLD"))["input_report_valid"])
