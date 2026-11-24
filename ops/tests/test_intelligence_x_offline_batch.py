import json
import unittest
from pathlib import Path
from intelligence_x_offline_batch import summarize, MAX_BATCH, MAX_BATCH_BYTES


class OfflineBatchTests(unittest.TestCase):
    def setUp(self):
        self.url = "https://club.example/news"
        raw = json.dumps({"success": True, "data": {"markdown": "Synthetic",
                         "metadata": {"sourceURL": self.url, "url": self.url,
                                      "statusCode": 200}}}).encode()
        self.row = dict(raw=raw, requested_url=self.url,
                        collected_at="2026-11-24T09:59:00Z", http_status=200)
        self.kw = dict(reviewed_urls={self.url}, now_utc="2026-11-24T10:00:00Z")

    def test_empty(self):
        self.assertEqual(summarize([], **self.kw)["total"], 0)

    def test_candidate_and_rejected(self):
        out = summarize([self.row, dict(self.row, http_status=429)], **self.kw)
        self.assertEqual((out["total"], out["candidates"], out["rejected"]), (2, 1, 1))
        self.assertEqual(out["status"], "HOLD")
        self.assertEqual(out["production_recommendations"], "DISABLED")
        self.assertEqual(out["external_calls"], 0)
        for key in ("source_authorized", "independently_verified",
                    "eligible_for_model_scoring", "corroboration_executed"):
            self.assertIs(out[key], False)
        self.assertNotIn(self.url, json.dumps(out))

    def test_duplicate(self):
        self.assertEqual(summarize([self.row, self.row], **self.kw)["rejected"], 1)

    def test_forged_flags(self):
        out = summarize([dict(self.row, status="PASS", source_authorized=True)], **self.kw)
        self.assertFalse(out["source_authorized"])

    def test_invalid_batch(self):
        for batch in (None, {}, [None], [self.row] * (MAX_BATCH + 1)):
            with self.subTest(batch_type=type(batch)), self.assertRaises(ValueError):
                summarize(batch, **self.kw)

    def test_total_byte_limit(self):
        with self.assertRaisesRegex(ValueError, "BATCH_BYTES_EXCEEDED"):
            summarize([dict(self.row, raw=b"x" * (MAX_BATCH_BYTES + 1))], **self.kw)

    def test_malformed_capture(self):
        out = summarize([{}, dict(self.row, raw=b"{")], **self.kw)
        self.assertEqual(out["rejected"], 2)

    def test_unreviewed_url(self):
        out = summarize([self.row], **dict(self.kw, reviewed_urls={"https://other.example/news"}))
        self.assertEqual(out["rejected"], 1)

    def test_workflow_is_inactive_and_local_only(self):
        root = Path(__file__).resolve().parents[2]
        w = json.loads((root / "research" / "intelligence_x" / "n8n_offline_demo.json").read_text())
        self.assertIs(w["active"], False)
        self.assertEqual([n["type"] for n in w["nodes"]],
                         ["n8n-nodes-base.manualTrigger", "n8n-nodes-base.code", "n8n-nodes-base.code"])
        self.assertFalse(any("credentials" in n for n in w["nodes"]))
        self.assertEqual(w["settings"]["timezone"], "Asia/Hong_Kong")
        self.assertIs(w["settings"]["saveManualExecutions"], False)
        self.assertEqual(w["pinData"], {})
        self.assertEqual(set(w["connections"]), {"Manual Trigger", "Synthetic Report"})


if __name__ == "__main__":
    unittest.main()
