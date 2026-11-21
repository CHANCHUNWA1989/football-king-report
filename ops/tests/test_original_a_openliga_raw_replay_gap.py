"""Real original archive format test, but all fixture bytes are synthetic.

These tests DO NOT run GitHub Sigstore verification, and never certify source.
"""
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from ops.openliga_capture_pack import prepare
from ops.tests.test_openliga_capture_pack import fixture, NOW
from ops.original_a_openliga_raw_replay_gap import audit, _sha_blob, SCHEMA


def local_captures(folder):
    raw_dir = folder / "raw"
    base = fixture(raw_dir)
    source_row = {
        "matchID": 123, "leagueId": 7, "leagueShortcut": "bl1",
        "leagueSeason": 2026, "matchDateTimeUTC": "2026-10-20T18:00:00Z",
        "matchIsFinished": False, "matchResults": [],
        "team1": {"teamId": 40, "teamName": "Team Alpha"},
        "team2": {"teamId": 50, "teamName": "Team Beta"},
    }
    raw = json.dumps([source_row], separators=(",", ":")).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (raw_dir / "openligadb.json").write_bytes(raw)
    base["sources"][0]["raw_sha256"] = sha
    base["sources"][0]["bytes"] = len(raw)
    (raw_dir / "manifest.json").write_text(json.dumps(base))
    target = folder / "subject" / "openliga-capture.tar"
    prepare(raw_dir, target, now=NOW)
    zipped = gzip.compress(target.read_bytes(), mtime=0)
    shadow = {
        "schema": "football-king-uncalibrated-shadow-1",
        "status": "SHADOW_ONLY", "as_of_utc": "2026-10-20T11:10:00Z",
        "production_recommendations": "DISABLED",
        "model_calibrated": False, "market_odds_available": False,
        "independently_verified_results": False, "predictions_count": 1,
        "sources": [{
            "league": "bundesliga", "status": "READY_RESEARCH",
            "source": "OpenLigaDB", "source_response_sha256": sha,
            "captured_utc": "2026-10-20T11:01:00Z",
        }],
        "predictions": [{
            "league": "bundesliga",
            "model": "poisson-shrinkage-unvalidated-v4.1",
            "production_recommendations": "DISABLED",
            "event_id": "openligadb:123",
            "prediction_utc": "2026-10-20T11:10:00Z",
            "kickoff_utc": "2026-10-20T18:00:00Z",
            "native_fixture_input": {
                "schema": "football-king-native-fixture-input-observation-v1",
                "status": "UNAUTHENTICATED", "provider": "OpenLigaDB",
                "league_shortcut": "bl1", "league_season": 2026,
                "match_id": 123, "home_team_id": 40, "away_team_id": 50,
                "league_id": 7, "source_response_sha256": sha,
                "source_identity_authenticated": False,
                "source_capture_authenticated": False,
                "raw_input_durably_archived": False,
                "native_ids_used_as_model_features": False,
                "eligible_for_model_scoring": False,
                "native_ids_from_same_response_as_gateway_fixture": True,
            }
        }]
    }
    return zipped, shadow


def make_manifest(capture, shadow):
    return {
        "schema": "football-king-two-original-archive-git-pins-v1",
        "production_recommendations": "DISABLED",
        "main_commit": "a" * 40,
        "archive_day": "2026/11/15",
        "capture": {
            "path": "openliga_capture_provenance/2026/11/15/43694406097-1/openliga-capture.tar.gz",
            "size": len(capture), "git_blob_sha1": _sha_blob(capture),
        },
        "shadow": {
            "path": "forecast_provenance/2026/11/15/43694349598-1/shadow.json.gz",
            "size": len(shadow), "git_blob_sha1": _sha_blob(shadow),
        },
    }


class OriginalAOpenLigaGapTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.capture, self.shadow = local_captures(Path(tmp.name))

    def go(self, *, capture=None, shadow=None, change_pin=True):
        a = self.capture if capture is None else capture
        b = gzip.compress(json.dumps(
            self.shadow if shadow is None else shadow,
            separators=(",", ":")).encode(), mtime=0)
        manifest = make_manifest(a, b)
        if not change_pin:
            manifest["capture"]["git_blob_sha1"] = "f" * 40
        return audit(manifest, a, b, now=NOW)

    def test_exact_raw_source_bytes_and_native_id_locally_replay(self):
        r = self.go()
        self.assertEqual(r["status"], "HOLD")
        self.assertEqual(r["reason"],
                         "SAME_ORIGINAL_SOURCE_BYTES_REPLAYED_BUT_SIGNER_NOT_REVERIFIED")
        self.assertTrue(r["byte_pins_checked"])
        self.assertTrue(r["controlled_capture_content_replayed"])
        self.assertEqual(r["local_same_response_id_and_kickoff_matches"], 1)
        self.assertEqual(r["matching_source_response_hash_count"], 1)
        self.assertFalse(r["independent_capture_attestation_reverified"])
        self.assertFalse(r["independent_forecast_attestation_reverified"])
        self.assertFalse(r["source_response_pair_certified"])
        self.assertEqual(r["certified_prospective_samples"], 0)
        self.assertFalse(r["positive_ev_verified"])
        self.assertEqual(r["production_recommendations"], "DISABLED")

    def test_sha_mismatch_rejected_before_any_parse(self):
        self.assertEqual(self.go(change_pin=False)["reason"],
                         "COMPRESSED_ARCHIVE_GIT_PIN_MISMATCH")

    def test_different_response_digest_not_accepted_as_same_source(self):
        self.shadow["predictions"][0]["native_fixture_input"]["source_response_sha256"] = "0" * 64
        r = self.go()
        self.assertEqual(r["local_same_response_id_and_kickoff_matches"], 0)
        self.assertEqual(r["reason"], "NO_IDENTICAL_A_SOURCE_RESPONSE_IN_PINNED_CAPTURE")

    def test_contradictory_native_team_orientation_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["home_team_id"] = 50
        self.shadow["predictions"][0]["native_fixture_input"]["away_team_id"] = 40
        r = self.go()
        self.assertEqual(r["reason"], "CONTRADICTORY_OR_UNVERIFIED_NATIVE_IDENTITY")
        self.assertNotIn("local_same_response_id_and_kickoff_matches", r)

    def test_wrong_kickoff_rejected(self):
        self.shadow["predictions"][0]["kickoff_utc"] = "2026-10-20T19:00:00Z"
        self.assertEqual(self.go()["reason"],
                         "CONTRADICTORY_OR_UNVERIFIED_NATIVE_IDENTITY")

    def test_unknown_native_match_id_rejected(self):
        p = self.shadow["predictions"][0]
        p["native_fixture_input"]["match_id"] = 999
        p["event_id"] = "openligadb:999"
        self.assertEqual(self.go()["reason"],
                         "CONTRADICTORY_OR_UNVERIFIED_NATIVE_IDENTITY")

    def test_bool_native_id_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["home_team_id"] = True
        self.assertEqual(self.go()["reason"],
                         "CONTRADICTORY_OR_UNVERIFIED_NATIVE_IDENTITY")

    def test_source_capture_did_not_precede_original_a(self):
        self.shadow["as_of_utc"] = "2026-10-20T11:02:00Z"
        self.assertEqual(self.go()["reason"], "SOURCE_CAPTURE_COMPLETED_AFTER_A_FORECAST")

    def test_untrusted_forecast_production_enabled_rejected(self):
        self.shadow["production_recommendations"] = "ENABLED"
        self.assertEqual(self.go()["reason"], "INVALID_OR_UNTRUSTED_A_FORECAST_ARCHIVE")

    def test_unsupported_model_never_counted_as_a(self):
        self.shadow["predictions"][0]["model"] = "penaltyblog"
        r = self.go()
        self.assertEqual(r["local_same_response_id_and_kickoff_matches"], 0)

    def test_raw_captured_provenance_is_not_gh_signature_verification(self):
        r = self.go()
        self.assertFalse(r["independent_capture_attestation_reverified"])
        self.assertFalse(r["independent_forecast_attestation_reverified"])
        self.assertFalse(r["publisher_identity_authenticated"])
        self.assertFalse(r["source_time_independently_attested"])
        self.assertFalse(r["eligible_for_model_scoring"])

    def test_relabelled_native_certification_rejected(self):
        self.shadow["predictions"][0]["native_fixture_input"]["source_identity_authenticated"] = True
        self.assertEqual(self.go()["reason"],
                         "CONTRADICTORY_OR_UNVERIFIED_NATIVE_IDENTITY")

    def test_missing_native_data_does_not_fabricate_source_ids(self):
        del self.shadow["predictions"][0]["native_fixture_input"]
        r = self.go()
        self.assertEqual(r["local_same_response_id_and_kickoff_matches"], 0)
        self.assertEqual(r["certified_prospective_samples"], 0)

    def test_empty_original_predictions_never_create_pair(self):
        self.shadow["predictions"] = []
        self.shadow["predictions_count"] = 0
        self.shadow["status"] = "HOLD"
        r = self.go()
        self.assertEqual(r["local_same_response_id_and_kickoff_matches"], 0)

    def test_two_source_reports_with_same_digest_is_ambiguous(self):
        self.shadow["sources"].append(copy.deepcopy(self.shadow["sources"][0]))
        self.assertEqual(self.go()["reason"], "ORIGINAL_A_SOURCE_REPORT_DIGEST_CONFLICT")

    def test_duplicate_raw_json_object_key_rejected(self):
        raw = gzip.compress(b'{"schema":1,"schema":2}', mtime=0)
        self.assertEqual(self.go(capture=raw)["status"], "HOLD")

    def test_duplicate_shadow_json_keys_are_blocked_with_valid_blob(self):
        raw = b'{"schema":"a","schema":"b"}'
        b = gzip.compress(raw, mtime=0)
        man = make_manifest(self.capture, b)
        self.assertEqual(audit(man, self.capture, b, now=NOW)["reason"],
                         "DUPLICATE_ARCHIVE_JSON_KEY")

    def test_corrupt_compressed_shadow_rejected(self):
        b = b"not-a-gzip"
        man = make_manifest(self.capture, b)
        r = audit(man, self.capture, b, now=NOW)
        self.assertEqual(r["status"], "HOLD")
        self.assertFalse(r["source_response_pair_certified"])

    def test_invalid_main_commit_pin_rejected(self):
        b = gzip.compress(json.dumps(self.shadow).encode(), mtime=0)
        man = make_manifest(self.capture, b)
        man["main_commit"] = "unknown"
        self.assertEqual(audit(man, self.capture, b, now=NOW)["reason"],
                         "INVALID_PINNED_RESEARCH_MANIFEST")

    def test_input_alias_file_path_not_allowed(self):
        b = gzip.compress(json.dumps(self.shadow).encode(), mtime=0)
        man = make_manifest(self.capture, b)
        man["capture"]["path"] = "../secret.gz"
        self.assertEqual(audit(man, self.capture, b, now=NOW)["reason"],
                         "INVALID_COMPRESSED_GIT_PIN")


if __name__ == "__main__":
    unittest.main()
