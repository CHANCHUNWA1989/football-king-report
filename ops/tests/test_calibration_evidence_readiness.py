"""Read-only genuine archive audit plus adversarial synthetic evidence tests."""
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from ops.calibration_evidence_readiness import audit, read_archive, SCHEMA

UTC = timezone.utc
BASE = datetime(2026, 11, 15, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]


def row(i=1):
    return {
        "key": f"synthetic:{i}",
        "league": "bundesliga",
        "forecast_utc": (BASE - timedelta(days=3)).isoformat(),
        "market_utc": (BASE - timedelta(days=3, hours=1)).isoformat(),
        "kickoff_utc": BASE.isoformat(),
        "y": 1,
        "p": [.55, .25, .20],
        "m": [.50, .30, .20],
        "fixture_result_source_independently_verified": False,
        "production_recommendations": "DISABLED",
    }


class EvidenceReadinessTests(unittest.TestCase):
    def test_actual_public_archive_remains_research_only(self):
        data = read_archive(REPO / "evidence" / "settled.json")
        result = audit(data)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["archive_rows"], len(data["samples"]))
        self.assertGreater(result["research_pair_shape_rows"], 0)
        self.assertEqual(result["certified_forward_rows"], 0)
        self.assertEqual(result["remaining_to_300"], 300)
        self.assertFalse(result["qualifies_for_calibration_training"])
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_fake_three_verified_flags_cannot_certify_oneself(self):
        rows = [row()]
        rows[0].update({
            "fixture_result_source_independently_verified": True,
            "fixture_identity_independently_verified": True,
            "forecast_provenance_independently_attested": True,
        })
        r = audit({"samples": rows})
        self.assertEqual(r["flag_claims"]["all_three_claimed"], 1)
        self.assertEqual(r["certified_forward_rows"], 0)
        self.assertFalse(r["independent_source_verifier_present"])
        self.assertFalse(r["qualifies_for_calibration_training"])

    def test_time_ordered_research_is_not_true_forward_proof(self):
        r = audit({"samples": [row()]})
        self.assertEqual(r["research_pair_shape_rows"], 1)
        self.assertEqual(r["chronologically_ordered_research_rows"], 1)
        self.assertEqual(r["certified_forward_rows"], 0)

    def test_future_market_cannot_pass_time_valid_research_gate(self):
        bad = row()
        bad["market_utc"] = (BASE + timedelta(minutes=1)).isoformat()
        result = audit({"samples": [bad]})
        self.assertEqual(result["chronologically_ordered_research_rows"], 0)
        self.assertEqual(result["reason"], "NO_TIME_VALID_RESEARCH_PAIRS")

    def test_candidate_without_timestamp_is_not_time_valid(self):
        bad = row()
        bad["forecast_utc"] = "2026-11-11T13:00:00"
        r = audit({"samples": [bad]})
        self.assertEqual(r["chronologically_ordered_research_rows"], 0)

    def test_boolean_outcome_rejected(self):
        bad = row()
        bad["y"] = True
        r = audit({"samples": [bad]})
        self.assertEqual(r["research_pair_shape_rows"], 0)
        self.assertEqual(r["unsafe_or_incomplete_rows"], 1)

    def test_malformed_probability_rejected(self):
        for p in ([.5, .4, .4], [True, .2, .3], [float("nan"), .2, .3],
                  [], [.0, .5, .5]):
            with self.subTest(p=p):
                bad = row()
                bad["p"] = p
                self.assertEqual(audit({"samples": [bad]})["research_pair_shape_rows"], 0)

    def test_duplicate_case_key_not_counted_twice(self):
        r = audit({"samples": [row(), row()]})
        self.assertEqual(r["research_pair_shape_rows"], 1)
        self.assertEqual(r["duplicate_case_keys"], 1)
        self.assertEqual(r["certified_forward_rows"], 0)

    def test_unsafe_production_flag_disqualifies_research_row(self):
        bad = row()
        bad["production_recommendations"] = "ENABLED"
        r = audit({"samples": [bad]})
        self.assertEqual(r["research_pair_shape_rows"], 0)
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_empty_or_malformed_archive_fails_closed(self):
        for bad in (None, [], {}, {"samples": {}}, {"samples": "abc"}):
            with self.subTest(bad=bad):
                r = audit(bad)
                self.assertEqual(r["status"], "HOLD")
                self.assertEqual(r["reason"], "INVALID_ARCHIVE_FORMAT")

    def test_file_json_duplicate_key_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "archive.json"
            path.write_text('{"samples":[],"samples":[]}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DUPLICATE_JSON_KEY"):
                read_archive(path)

    def test_file_with_nan_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "bad.json"
            path.write_text('{"samples": [NaN]}', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_archive(path)

    def test_does_not_mutate_original_rows(self):
        source = {"samples": [row()]}
        original = json.dumps(source, sort_keys=True)
        audit(source)
        self.assertEqual(original, json.dumps(source, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
