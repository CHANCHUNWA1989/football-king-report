import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from shadow_external_evidence_probe import probe


class ExternalEvidenceProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.coverage = self.root / "coverage.json"
        self.coverage.write_text(json.dumps({"matured_unmatched_fixtures": [
            {"fixture_id": "match-1", "home": "Alpha FC", "away": "Beta FC"}
        ]}), encoding="utf-8")

    def prepare(self, html):
        body = html.encode()
        (self.raw / "dfb.html").write_bytes(body)
        (self.raw / "manifest.json").write_text(json.dumps({
            "status": "HOLD", "eligible_for_model_scoring": False,
            "sources": [{"provider": "DFB", "status": "FETCHED_UNVERIFIED",
                         "raw_file": "dfb.html", "raw_sha256": hashlib.sha256(body).hexdigest()}]
        }), encoding="utf-8")

    def test_script_text_does_not_count_as_match(self):
        self.prepare("<script>Alpha FC Beta FC</script><main>Other content</main>")
        result = probe(self.raw, self.coverage)
        self.assertEqual(result["source_probes"][0]["names_nearby"], 0)
        self.assertFalse(result["eligible_for_model_scoring"])

    def test_whitespace_normalization_and_nearby_names(self):
        self.prepare("<div>Alpha FC</div>\n   <div>Beta FC</div>")
        result = probe(self.raw, self.coverage)
        match = result["source_probes"][0]["fixture_text_checks"][0]
        self.assertTrue(match["names_nearby"])
        self.assertIn("alpha fc beta fc", match["context_excerpt"])
        self.assertFalse(result["independently_verified"])

    def test_score_like_tokens_never_certified(self):
        self.prepare("<article>Alpha FC 2:1 Beta FC</article>")
        result = probe(self.raw, self.coverage)
        match = result["source_probes"][0]["fixture_text_checks"][0]
        self.assertEqual(match["score_like_tokens_unverified"][0]["raw"], "2:1")
        self.assertTrue(result["score_candidates_are_unverified"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertFalse(result["independently_verified"])

    def test_hash_mismatch_rejected(self):
        self.prepare("<div>Alpha FC Beta FC</div>")
        (self.raw / "dfb.html").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "RAW_HASH_MISMATCH"):
            probe(self.raw, self.coverage)


if __name__ == "__main__":
    unittest.main()
