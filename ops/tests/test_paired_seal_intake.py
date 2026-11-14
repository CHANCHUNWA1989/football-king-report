import hashlib
import json
import unittest
from ops.paired_seal_intake import pair


def receipt(model, *, as_of="2026-11-08T18:00:00+00:00"):
    forecast = {"schema": "football-king-forecast-seal-input-v1",
                "source_namespace": "synthetic", "fixture_id": "fixture-1",
                "kickoff_utc": "2026-11-08T20:00:00+00:00",
                "as_of_utc": as_of, "model_id": model, "model_version": "v1",
                "probabilities": [.5, .3, .2], "production_recommendations": "DISABLED"}
    canonical = json.dumps(forecast, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False)
    return {"schema": "football-king-forecast-receipt-v1", "status": "RESEARCH_ONLY",
            "capture_utc": "2026-11-08T19:00:00+00:00",
            "payload_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "forecast": forecast, "independently_timestamped": False,
            "production_recommendations": "DISABLED"}


class PairedSealIntakeTests(unittest.TestCase):
    def test_valid_local_pair_still_hold_without_external_proof(self):
        r = pair(receipt("original"), receipt("challenger"))
        self.assertEqual(r["reason"], "INDEPENDENT_TIMESTAMP_ATTESTATION_MISSING")
        self.assertTrue(r["local_hashes_valid"])

    def test_different_cutoffs_hold(self):
        self.assertEqual(pair(receipt("a"), receipt("b", as_of="2026-11-08T17:00:00+00:00"))["reason"],
                         "NOT_SAME_FIXTURE_OR_CUTOFF")

    def test_hash_tamper_hold(self):
        a = receipt("a")
        a["forecast"]["probabilities"] = [.2, .3, .5]
        self.assertEqual(pair(a, receipt("b"))["reason"], "HASH_MISMATCH")

    def test_duplicate_model_hold(self):
        self.assertEqual(pair(receipt("a"), receipt("a"))["reason"], "DUPLICATE_MODEL")

    def test_attestation_flag_not_trusted(self):
        a, b = receipt("a"), receipt("b")
        a["independently_timestamped"] = True
        b["independently_timestamped"] = True
        self.assertEqual(pair(a, b)["reason"], "EXTERNAL_ATTESTATION_NOT_VERIFIED")

    def test_post_kickoff_capture_hold(self):
        a = receipt("a")
        a["capture_utc"] = "2026-11-08T21:00:00+00:00"
        self.assertEqual(pair(a, receipt("b"))["reason"], "LOOKAHEAD_OR_INVALID_CAPTURE")


if __name__ == "__main__":
    unittest.main()
