"""Synthetic tests: archive matching is not provider/forecast attestation."""
import copy
from hashlib import sha1
import json
import unittest

from ops.paired_real_archive_gap_audit import audit_bytes, MAX_BYTES


def archive():
    rows = []
    for index in range(2):
        kickoff = "2026-11-08T20:00:00+00:00"
        home, away = "team-" + str(index * 2), "team-" + str(index * 2 + 1)
        row = {
            "key": json.dumps(["bundesliga", home, away, kickoff]),
            "league": "bundesliga", "kickoff_utc": kickoff,
            "forecast_utc": "2026-11-08T18:00:00+00:00",
            "market_utc": "2026-11-08T17:00:00+00:00",
            "y": index, "p": [.5, .3, .2], "m": [.45, .3, .25],
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }
        rows.append(row)
    rows[0]["ab"] = [.5, .3, .2]
    rows[0]["ab_model"] = "probability-shrink-to-uniform-fixed-0.15-v1"
    rows[1]["c"] = [.5, .3, .2]
    rows[1]["c_model"] = "market-anchored-fixed-25pct-model-75pct-consensus-v1"
    rows[0]["forecast_event_id"] = "self-claimed-event"
    rows[0]["source_fixture_identity"] = {"provider": "OpenLigaDB", "match_id": "1234"}
    return {
        "schema": "football-king-forward-research-1",
        "checked_utc": "2026-11-12T00:00:00Z",
        "n": len(rows), "samples": rows,
        "results_independently_verified": False,
        "profitability_verified": False,
        "production_recommendations": "DISABLED",
    }


def check(data, *, sha=None):
    raw = json.dumps(data, ensure_ascii=False, allow_nan=True).encode("utf-8")
    valid = sha1(b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw).hexdigest()
    return audit_bytes(raw, expected_git_blob_sha1=valid if sha is None else sha)


class RealArchiveGapTests(unittest.TestCase):
    def setUp(self):
        self.data = archive()

    def test_normal_legacy_never_certifies_penaltyblog(self):
        result = check(self.data)
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(result["archive_git_blob_sha1_matched"])
        self.assertEqual(result["legacy_settled_research_rows"], 2)
        self.assertEqual(result["legacy_p_model_vectors"], 2)
        self.assertEqual(result["legacy_m_market_probability_vectors"], 2)
        self.assertEqual(result["legacy_ab_shrink_vectors_not_penaltyblog"], 1)
        self.assertEqual(result["legacy_c_market_anchored_vectors_not_penaltyblog"], 1)
        self.assertEqual(result["rows_with_forecast_event_id_unattested"], 1)
        self.assertEqual(result["rows_with_native_source_fixture_id_unattested"], 1)
        self.assertEqual(result["rows_with_penaltyblog_native_forecast_snapshot"], 0)
        self.assertEqual(result["paired_penaltyblog_forecasts_certified"], 0)
        self.assertEqual(result["certified_prospective_samples"], 0)
        self.assertFalse(result["positive_ev_verified"])
        self.assertFalse(result["result_truth_independently_verified"])
        self.assertFalse(result["market_quote_executable_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_valid_hash_does_not_override_trust_flags(self):
        self.data["samples"][0]["eligible_for_model_scoring"] = True
        self.assertEqual(check(self.data)["reason"], "SELF_CERTIFIED_LEGACY_RECORD_REJECTED")

    def test_rehashed_fake_independent_result_still_rejected(self):
        self.data["samples"][0]["fixture_result_source_independently_verified"] = True
        self.assertEqual(check(self.data)["reason"], "SELF_CERTIFIED_LEGACY_RECORD_REJECTED")

    def test_forged_penaltyblog_fields_rejected(self):
        self.data["samples"][0]["penaltyblog_model_id"] = "dixon-coles"
        self.assertEqual(check(self.data)["reason"], "UNEXPECTED_LEGACY_ROW_SCHEMA")

    def test_unrecognized_ab_model_cannot_be_relabelled(self):
        self.data["samples"][0]["ab_model"] = "penaltyblog-dixon-coles"
        self.assertEqual(check(self.data)["reason"], "UNRECOGNIZED_LEGACY_CHALLENGER")

    def test_ab_without_model_label_rejected(self):
        del self.data["samples"][0]["ab_model"]
        self.assertEqual(check(self.data)["reason"], "UNRECOGNIZED_LEGACY_CHALLENGER")

    def test_invalid_c_probabilities_rejected(self):
        self.data["samples"][1]["c"] = [True, .3, .7]
        self.assertEqual(check(self.data)["reason"], "UNRECOGNIZED_LEGACY_CHALLENGER")

    def test_boolean_y_rejected(self):
        self.data["samples"][0]["y"] = True
        self.assertEqual(check(self.data)["reason"], "INVALID_LEGACY_OUTCOME")

    def test_boolean_p_rejected(self):
        self.data["samples"][0]["p"] = [True, 0.0, 0.0]
        self.assertEqual(check(self.data)["reason"], "INVALID_LEGACY_PROBABILITIES")

    def test_duplicate_fixture_rejected(self):
        self.data["samples"][1] = copy.deepcopy(self.data["samples"][0])
        self.assertEqual(check(self.data)["reason"], "DUPLICATE_OR_INVALID_FIXTURE_KEY")

    def test_wrong_native_identity_rejected(self):
        self.data["samples"][1]["key"] = json.dumps(
            ["laliga", "team-2", "team-3", "2026-11-08T20:00:00Z"])
        self.assertEqual(check(self.data)["reason"], "INVALID_LEGACY_FIXTURE_KEY")

    def test_forecast_after_kickoff_rejected(self):
        self.data["samples"][0]["forecast_utc"] = "2026-11-08T21:00:00Z"
        self.assertEqual(check(self.data)["reason"], "INVALID_LEGACY_CHRONOLOGY")

    def test_invalid_result_provider_id_rejected(self):
        self.data["samples"][0]["source_fixture_identity"]["match_id"] = 1234
        self.assertEqual(check(self.data)["reason"], "INVALID_UNATTESTED_SOURCE_ID")

    def test_any_production_enabled_rejected(self):
        self.data["production_recommendations"] = "ENABLED"
        self.assertEqual(check(self.data)["reason"], "UNSAFE_OR_UNEXPECTED_ARCHIVE")

    def test_n_mismatch_rejected(self):
        self.data["n"] = 1
        self.assertEqual(check(self.data)["reason"], "UNSAFE_OR_UNEXPECTED_ARCHIVE")

    def test_wrong_expected_git_blob_ref_rejected_before_json(self):
        self.assertEqual(check(self.data, sha="f" * 40)["reason"], "ARCHIVE_GIT_BLOB_SHA_MISMATCH")

    def test_invalid_blob_sha_rejected(self):
        self.assertEqual(check(self.data, sha="not-a-sha")["reason"], "INVALID_PINNED_GIT_BLOB_SHA")

    def test_oversize_archive_rejected(self):
        self.assertEqual(audit_bytes(b"Z" * (MAX_BYTES + 1),
            expected_git_blob_sha1="a" * 40)["reason"], "INVALID_ARCHIVE_BYTE_SIZE")

    def test_duplicate_json_object_key_rejected_with_valid_blob_hash(self):
        raw = b'{"schema":"a","schema":"b"}'
        sha = sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
        self.assertEqual(audit_bytes(raw, expected_git_blob_sha1=sha)["reason"],
                         "DUPLICATE_JSON_KEY")

    def test_nonfinite_json_rejected_with_valid_blob_hash(self):
        raw = json.dumps(self.data).replace('"n": 2', '"n": NaN').encode()
        sha = sha1(b"blob " + str(len(raw)).encode() + b"\x00" + raw).hexdigest()
        self.assertEqual(audit_bytes(raw, expected_git_blob_sha1=sha)["reason"],
                         "NONFINITE_JSON")

    def test_unattested_flags_cannot_promote_archived_samples(self):
        self.data["samples"][0]["independently_verified"] = True
        self.assertEqual(check(self.data)["reason"], "SELF_CERTIFIED_LEGACY_RECORD_REJECTED")


if __name__ == "__main__":
    unittest.main()
