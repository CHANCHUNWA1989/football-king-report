import unittest
from ops.private_soccerdata_research_manifest import build_research_manifest, verify_research_manifest


def row(i, day, outcome):
    return {"source": "soccerdata.MatchHistory", "source_index": str(i),
            "source_local_match_datetime": day + "T12:00:00",
            "kickoff_time_verified": False, "pre_match_features_verified": False,
            "outcome": outcome}


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.records = [row(1, "2026-01-01", "H"), row(2, "2026-01-01", "D"),
                        row(3, "2026-01-02", "A")]

    def test_reproducible_for_reordered_input(self):
        a = build_research_manifest(self.records, min_train=2)
        b = build_research_manifest(list(reversed(self.records)), min_train=2)
        self.assertEqual(a, b)
        self.assertEqual(verify_research_manifest(self.records, a)["status"], "MATCH")
        self.assertFalse(a["independent_provenance_verified"])

    def test_modified_result_detected(self):
        a = build_research_manifest(self.records, min_train=2)
        changed = [dict(x) for x in self.records]
        changed[0]["outcome"] = "A"
        with self.assertRaisesRegex(ValueError, "MISMATCH"):
            verify_research_manifest(changed, a)

    def test_modified_report_detected(self):
        a = build_research_manifest(self.records, min_train=2)
        a["baseline_result_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "MISMATCH"):
            verify_research_manifest(self.records, a)

    def test_invalid_manifest_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_MANIFEST"):
            verify_research_manifest(self.records, {})


if __name__ == "__main__":
    unittest.main()
