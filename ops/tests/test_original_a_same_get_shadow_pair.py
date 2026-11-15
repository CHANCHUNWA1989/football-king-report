"""Synthetic original-A byte pairing, native-ID and immutable replay tests.

These source bytes ARE FABRICATED. They establish only code semantics, never
original publisher legitimacy or independent forecast timing.
"""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from ops.original_a_same_get_private_seal import seal
from ops.original_a_same_get_shadow_pair import create, replay
from ops.tests.test_penaltyblog_a_shadow_native_handoff import shadow, z, A, KO


def data():
    response = [{
        "matchID": 999999, "leagueId": 100, "leagueShortcut": "bl1",
        "leagueSeason": 2026, "matchDateTimeUTC": z(KO),
        "team1": {"teamId": 101, "teamName": "Visible Team A"},
        "team2": {"teamId": 102, "teamName": "Visible Team B"},
        "matchIsFinished": False, "matchResults": [],
    }]
    return json.dumps(response, separators=(",", ":")).encode("utf-8")


class ExactOriginalGetShadowLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.source = self.home / "source"
        self.paired = self.home / "links"
        self.source.mkdir(mode=0o700)
        self.paired.mkdir(mode=0o700)
        self.body = data()
        self.s = shadow()
        self.update_digests()
        self.base_original = {
            "status": "READY_RESEARCH", "source": "OpenLigaDB",
            "league": "bundesliga", "season": "2026-27",
            "sha256": hashlib.sha256(self.body).hexdigest(),
            "_same_response_source_sha256": hashlib.sha256(self.body).hexdigest(),
            "captured_utc": z(A - timedelta(minutes=5)),
        }
        self.seal_source()
        self.shadow = self.home / "shadow.json"
        self.write_shadow()

    def update_digests(self):
        digest = hashlib.sha256(self.body).hexdigest()
        self.s["sources"][0]["source_response_sha256"] = digest
        self.s["sources"][0]["private_same_get_raw_sha256_unattested"] = digest
        self.s["sources"][0]["private_source_capture_independently_attested"] = False
        self.s["predictions"][0]["native_fixture_input"]["source_response_sha256"] = digest

    def seal_source(self, *, now=None):
        r = seal(self.source, body=self.body, original=self.base_original,
                 season="2026-27", league="bundesliga",
                 now=now or A - timedelta(minutes=4))
        self.private_sha = r["private_bundle_sha256_unattested"]
        self.s["sources"][0]["private_same_get_bundle_sha256_unattested"] = self.private_sha

    def write_shadow(self):
        self.shadow.write_text(json.dumps(self.s, sort_keys=True), encoding="utf-8")
        self.shadow.chmod(0o600)

    def create(self):
        self.write_shadow()
        return create(self.shadow, original_dir=self.source, pair_dir=self.paired,
                      source_bundle_sha256=self.private_sha)

    def link_file(self, result):
        return self.paired / (result["private_link_sha256_unattested"] +
                              ".a-source-link-private.tar")

    def test_genuine_same_bytes_synthetic_a_fixture_replays_no_certification(self):
        result = self.create()
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "LOCAL_SAME_GET_A_LINK_UNATTESTED")
        self.assertEqual(result["matched_native_fixture_count"], 1)
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertFalse(result["source_publisher_authenticated"])
        self.assertFalse(result["source_timestamp_attested"])
        self.assertFalse(result["forecast_timestamp_attested"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(result["certified_prospective_samples"], 0)
        path = self.link_file(result)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        got = replay(path, original_dir=self.source,
                     source_bundle_sha256=self.private_sha,
                     expected_pair_sha256=result["private_link_sha256_unattested"])
        self.assertTrue(got["locally_replayable_byte_identity"])
        self.assertEqual(got["matched_native_fixture_count"], 1)
        self.assertEqual(got["status"], "HOLD")
        self.assertFalse(got["source_timestamp_attested"])

    def test_same_link_repeated_cannot_overwrite(self):
        first = self.create()
        before = self.link_file(first).read_bytes()
        with self.assertRaises(FileExistsError):
            self.create()
        self.assertEqual(self.link_file(first).read_bytes(), before)
        self.assertEqual(len(list(self.paired.iterdir())), 1)

    def test_missing_source_bundle_rejected(self):
        self.private_sha = "0" * 64
        self.s["sources"][0]["private_same_get_bundle_sha256_unattested"] = self.private_sha
        with self.assertRaises((ValueError, OSError)):
            self.create()
        self.assertFalse(list(self.paired.iterdir()))

    def test_crossrun_source_digest_cannot_be_substituted(self):
        self.s["sources"][0]["source_response_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "A_SHADOW_SOURCE_NOT_SAME_GET_OR_NOT_PRIVATE"):
            self.create()

    def test_claimed_source_digest_not_equal_private_digest_rejected(self):
        self.s["sources"][0]["private_same_get_raw_sha256_unattested"] = "1" * 64
        with self.assertRaises(ValueError):
            self.create()

    def test_source_tar_tamper_after_new_link_replay_rejected(self):
        good = self.create()
        rawfile = self.source / (self.private_sha + ".openliga-private.tar")
        rawfile.write_bytes(rawfile.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "PRIVATE_CAPTURE_BUNDLE_HASH_MISMATCH"):
            replay(self.link_file(good), original_dir=self.source,
                   source_bundle_sha256=self.private_sha,
                   expected_pair_sha256=good["private_link_sha256_unattested"])

    def test_shadow_file_tamper_after_link_cannot_change_the_link(self):
        good = self.create()
        path = self.link_file(good)
        before = path.read_bytes()
        self.shadow.write_text('{"fake":true}')
        with self.assertRaises(ValueError):
            self.create()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(replay(path, original_dir=self.source,
                         source_bundle_sha256=self.private_sha,
                         expected_pair_sha256=good["private_link_sha256_unattested"])["status"], "HOLD")

    def test_private_link_tar_bytes_tamper_replay_rejected(self):
        good = self.create()
        path = self.link_file(good)
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "PRIVATE_LINK_HASH_MISMATCH"):
            replay(path, original_dir=self.source, source_bundle_sha256=self.private_sha,
                   expected_pair_sha256=good["private_link_sha256_unattested"])

    def test_swapped_native_team_ids_rejected(self):
        p = self.s["predictions"][0]["native_fixture_input"]
        p["home_team_id"], p["away_team_id"] = p["away_team_id"], p["home_team_id"]
        with self.assertRaisesRegex(ValueError, "ORIGINAL_RAW_A_ID_OR_KICKOFF_CONTRADICTION"):
            self.create()

    def test_unknown_match_id_rejected(self):
        p = self.s["predictions"][0]
        p["event_id"] = "openligadb:999998"
        p["native_fixture_input"]["match_id"] = 999998
        with self.assertRaisesRegex(ValueError, "MISSING_OR_DUPLICATE_ORIGINAL_FIXTURE"):
            self.create()

    def test_same_provider_but_wrong_kickoff_rejected(self):
        self.s["predictions"][0]["kickoff_utc"] = z(KO + timedelta(minutes=5))
        with self.assertRaisesRegex(ValueError, "ORIGINAL_RAW_A_ID_OR_KICKOFF_CONTRADICTION"):
            self.create()

    def test_missing_native_id_rejected_not_filtered(self):
        del self.s["predictions"][0]["native_fixture_input"]
        with self.assertRaisesRegex(ValueError, "INVALID_BUNDESLIGA_NATIVE_A_PREDICTION"):
            self.create()
        self.assertFalse(list(self.paired.iterdir()))

    def test_duplicate_prediction_same_event_rejected(self):
        self.s["predictions"].append(copy.deepcopy(self.s["predictions"][0]))
        self.s["predictions_count"] = 2
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OR_MISMATCHED_NATIVE_A_EVENT"):
            self.create()

    def test_bad_source_capture_time_rejected(self):
        self.s["sources"][0]["captured_utc"] = z(A + timedelta(minutes=2))
        with self.assertRaisesRegex(ValueError, "SOURCE_RECEIVED_OUTSIDE_A_RUN"):
            self.create()

    def test_private_seal_missing_from_shadow_rejected(self):
        del self.s["sources"][0]["private_same_get_bundle_sha256_unattested"]
        with self.assertRaises(ValueError):
            self.create()

    def test_replay_a_clock_cannot_be_used(self):
        del self.s["generation_clock"]
        with self.assertRaisesRegex(ValueError, "REPLAY_OR_UNTRUSTED_ORIGINAL_A_CLOCK"):
            self.create()

    def test_claimed_authenticated_a_source_fails(self):
        self.s["predictions"][0]["native_fixture_input"]["source_identity_authenticated"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_BUNDESLIGA_NATIVE_A_PREDICTION"):
            self.create()

    def test_not_independently_attested_private_seal_must_be_false(self):
        self.s["sources"][0]["private_source_capture_independently_attested"] = True
        with self.assertRaises(ValueError):
            self.create()

    def test_training_hash_must_be_present(self):
        del self.s["predictions"][0]["training_observations_sha256"]
        with self.assertRaisesRegex(ValueError, "INVALID_OR_UNPINNED_A_PROBABILITIES"):
            self.create()

    def test_probability_boolean_must_be_rejected(self):
        self.s["predictions"][0]["p_home"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_OR_UNPINNED_A_PROBABILITIES"):
            self.create()

    def test_source_finished_after_original_a_batch_fails(self):
        # Rebuild a new private tar with the SAME raw source but with a seal
        # timestamp later than the saved A batch-completed UTC.
        r = seal(self.source, body=self.body, original=self.base_original,
                 season="2026-27", league="bundesliga",
                 now=A + timedelta(minutes=1))
        self.private_sha = r["private_bundle_sha256_unattested"]
        self.s["sources"][0]["private_same_get_bundle_sha256_unattested"] = self.private_sha
        with self.assertRaisesRegex(ValueError, "ORIGINAL_SOURCE_CLAIM_DOES_NOT_MATCH_A"):
            self.create()

    def test_private_output_directory_must_not_be_world_readable(self):
        self.paired.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "UNSAFE_PRIVATE_CAPTURE_DIRECTORY"):
            self.create()

    def test_source_link_directory_cannot_be_same(self):
        self.write_shadow()
        with self.assertRaisesRegex(ValueError, "SOURCE_AND_LINK_DIRECTORIES_MUST_BE_SEPARATE"):
            create(self.shadow, original_dir=self.source, pair_dir=self.source,
                   source_bundle_sha256=self.private_sha)

    def test_shadow_symlink_must_be_rejected(self):
        alias = self.home / "shadow-alias.json"
        alias.symlink_to(self.shadow)
        with self.assertRaisesRegex(ValueError, "UNSAFE_PRIVATE_SOURCE_PATH"):
            create(alias, original_dir=self.source, pair_dir=self.paired,
                   source_bundle_sha256=self.private_sha)

    def test_shadow_hardlink_must_be_rejected(self):
        alias = self.home / "shadow-hardlink.json"
        os.link(self.shadow, alias)
        with self.assertRaisesRegex(ValueError, "UNSAFE_PRIVATE_SOURCE_FILE"):
            self.create()

    def test_invalid_eligible_forecast_flag_fails(self):
        self.s["production_recommendations"] = "ENABLED"
        with self.assertRaisesRegex(ValueError, "INVALID_OR_UNSAFE_A_SHADOW"):
            self.create()

    def test_duplicate_raw_original_match_id_fails(self):
        duplicate = json.loads(self.body)
        duplicate.append(copy.deepcopy(duplicate[0]))
        raw_new = json.dumps(duplicate, separators=(",", ":")).encode()
        original = dict(self.base_original)
        original["sha256"] = hashlib.sha256(raw_new).hexdigest()
        original["_same_response_source_sha256"] = original["sha256"]
        r = seal(self.source, body=raw_new, original=original,
                 season="2026-27", league="bundesliga",
                 now=A - timedelta(minutes=4))
        self.private_sha = r["private_bundle_sha256_unattested"]
        self.s["sources"][0]["source_response_sha256"] = original["sha256"]
        self.s["sources"][0]["private_same_get_raw_sha256_unattested"] = original["sha256"]
        self.s["sources"][0]["private_same_get_bundle_sha256_unattested"] = self.private_sha
        self.s["predictions"][0]["native_fixture_input"]["source_response_sha256"] = original["sha256"]
        with self.assertRaisesRegex(ValueError, "MISSING_OR_DUPLICATE_ORIGINAL_FIXTURE"):
            self.create()

    def test_private_link_cannot_gain_certification_by_self_claim(self):
        good = self.create()
        r = replay(self.link_file(good), original_dir=self.source,
                   source_bundle_sha256=self.private_sha,
                   expected_pair_sha256=good["private_link_sha256_unattested"])
        for k in ("positive_ev_verified", "source_publisher_authenticated",
                  "source_timestamp_attested", "forecast_timestamp_attested",
                  "eligible_for_model_scoring", "model_promoted"):
            self.assertIs(r[k], False, k)

    def test_real_original_a_get_not_performed_by_these_tests(self):
        self.assertFalse(any(self.paired.iterdir()))


if __name__ == "__main__":
    unittest.main()
