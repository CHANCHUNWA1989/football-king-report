"""Offline-only evidence qualification: claimed flags never certify 1X2 outcomes."""
import hashlib
import json
import unittest

from ops.vnext_legacy_settled_readiness import audit_archive_bytes


def archive():
    return {
        "schema": "synthetic-research-archive",
        "checked_utc": "2026-11-15T07:00:00+00:00",
        "production_recommendations": "DISABLED",
        "results_independently_verified": False,
        "profitability_verified": False,
        "samples": [{
            "key": "synthetic-match-001",
            "league": "synthetic",
            "forecast_utc": "2026-11-14T17:00:00Z",
            "market_utc": "2026-11-14T16:00:00Z",
            "kickoff_utc": "2026-11-14T18:00:00Z",
            "p": [0.5, 0.3, 0.2],
            "m": [0.4, 0.3, 0.3],
            "y": 0,
            "fixture_result_source_independently_verified": False,
            "production_recommendations": "DISABLED",
        }],
    }


def render(doc):
    data = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sha = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    return data, sha


class LegacySettledReadinessTests(unittest.TestCase):
    def check(self, doc=None):
        raw, expected = render(archive() if doc is None else doc)
        return audit_archive_bytes(raw, expected_git_blob_sha1=expected)

    def test_valid_synthetic_row_is_observed_not_certified(self):
        x = self.check()
        self.assertEqual(x["status"], "HOLD")
        self.assertEqual(x["archived_rows"], 1)
        self.assertEqual(x["structurally_checked_rows"], 1)
        self.assertEqual(x["certified_prospective_rows"], 0)
        self.assertEqual(x["production_recommendations"], "DISABLED")
        self.assertFalse(x["positive_ev_verified"])
        self.assertFalse(x["commercial_data_rights_verified"])
        self.assertEqual(x["field_coverage"]["fixture_identity"], 0)
        self.assertEqual(x["field_coverage"]["result_original_digest"], 0)

    def test_same_length_byte_tampering_rejected_by_git_blob(self):
        raw, expected = render(archive())
        changed = raw.replace(b"synthetic-match-001", b"synthetic-match-002")
        self.assertEqual(len(changed), len(raw))
        with self.assertRaisesRegex(ValueError, "ARCHIVE_GIT_BLOB_MISMATCH"):
            audit_archive_bytes(changed, expected_git_blob_sha1=expected)

    def test_certification_flags_cannot_self_approve_sample(self):
        forged = archive()
        forged["results_independently_verified"] = True
        forged["profitability_verified"] = True
        row = forged["samples"][0]
        row["fixture_result_source_independently_verified"] = True
        row["independently_verified"] = True
        row["eligible_for_model_scoring"] = True
        row["source_fixture_identity"] = {"provider":"claimed", "match_id":"fake-123"}
        row["model_artifact_sha256"] = "a"*64
        row["fixture_result_source"] = "https://example.org/unverified"
        row["source_raw_sha256"] = "b"*64
        row["external_forecast_witness_verified"] = True
        x = self.check(forged)
        self.assertEqual(x["certified_prospective_rows"], 0)
        self.assertEqual(x["unsupported_certification_claim_rows"], 1)
        self.assertEqual(x["status"], "HOLD")
        self.assertEqual(x["field_coverage"]["fixture_identity"], 1)
        self.assertEqual(x["field_coverage"]["result_original_digest"], 1)
        self.assertFalse(x["result_source_identity_independently_verified"])

    def test_row_without_valid_chronology_fails(self):
        invalid = archive()
        invalid["samples"][0]["forecast_utc"] = "2026-11-14T19:00:00Z"
        with self.assertRaisesRegex(ValueError, "INVALID_ARCHIVED_CHRONOLOGY"):
            self.check(invalid)

    def test_row_without_safe_probability_fails(self):
        for vector in ([0.9,0.9,0.9], [float("nan"),0.5,0.5], [True,0.5,0.5]):
            with self.subTest(vector=vector):
                invalid=archive()
                invalid["samples"][0]["p"]=vector
                with self.assertRaises(ValueError):
                    self.check(invalid)

    def test_duplicate_json_keys_are_rejected_not_silently_overwritten(self):
        raw=b'{"samples":[],"samples":[],"production_recommendations":"DISABLED"}'
        blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ARCHIVE_JSON_KEY"):
            audit_archive_bytes(raw, expected_git_blob_sha1=blob)

    def test_duplicate_rows_rejected(self):
        invalid=archive()
        invalid["samples"].append(dict(invalid["samples"][0]))
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ARCHIVED_FIXTURE_KEY"):
            self.check(invalid)

    def test_large_or_missing_content_fails(self):
        with self.assertRaises(ValueError):
            audit_archive_bytes(b"", expected_git_blob_sha1="a"*40)
        with self.assertRaises(ValueError):
            audit_archive_bytes(b" "*8_000_001, expected_git_blob_sha1="a"*40)

    def test_unverified_result_source_string_is_not_authenticated_original(self):
        doc=archive()
        r=doc["samples"][0]
        r["source_fixture_identity"]={"provider":"OpenLigaDB", "match_id":"123"}
        r["fixture_result_source"]="https://fake-provider.example/score.json"
        r["source_raw_sha256"]="c"*64
        x=self.check(doc)
        self.assertEqual(x["field_coverage"]["fixture_identity"],1)
        self.assertEqual(x["field_coverage"]["result_source_reference"],1)
        self.assertEqual(x["field_coverage"]["result_original_digest"],1)
        self.assertEqual(x["certified_prospective_rows"],0)
        self.assertFalse(x["result_source_identity_independently_verified"])
        self.assertFalse(x["external_witness_independently_verified"])

    def test_top_level_or_row_production_enable_is_hard_error(self):
        for scope in ("top","row"):
            with self.subTest(scope=scope):
                invalid=archive()
                if scope=="top":
                    invalid["production_recommendations"]="ENABLED"
                else:
                    invalid["samples"][0]["production_recommendations"]="ENABLED"
                with self.assertRaisesRegex(ValueError, "UNSAFE_ARCHIVE"):
                    self.check(invalid)

    def test_no_self_supplied_source_pin_for_missing_or_invalid_digest(self):
        raw,_=render(archive())
        for val in ("0"*39, "g"*40, None):
            with self.subTest(val=val):
                with self.assertRaises(ValueError):
                    audit_archive_bytes(raw, expected_git_blob_sha1=val)

    def test_archive_missing_result_before_kickoff_cannot_be_scored_as_prospective(self):
        x=self.check()
        self.assertFalse(x["external_witness_independently_verified"])
        self.assertEqual(x["missing_external_forecast_proof_rows"],1)
        self.assertEqual(x["missing_independent_result_original_rows"],1)


if __name__=="__main__":
    unittest.main()
