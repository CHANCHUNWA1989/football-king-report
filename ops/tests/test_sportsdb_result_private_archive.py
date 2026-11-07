"""Synthetic private GitHub round-trip for real-result raw evidence transport.

All transport tests use a fake in-memory GitHub and synthetic event JSON.
They do not add a certified football result or create a real private archive.
"""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from ops import private_response_archive as destination
from ops import sportsdb_result_private_archive as archive
from ops.sportsdb_event_capture import capture, CaptureError
from ops.tests.test_private_response_archive import FakeGitHub, ENV
from ops.tests.test_sportsdb_event_capture import original, second

SHA = "a" * 40
RUN = "9001"
ATTEMPT = "1"
TOKEN = ENV["PRIVATE_ARCHIVE_TOKEN"]


def receipt(event_id):
    return {
        "http_status": 200,
        "http_final_url": "https://www.thesportsdb.com/api/v1/json/123/lookupevent.php?id=" + event_id,
        "http_content_type": "application/json",
        "http_redirects_followed": False,
        "request_started_utc": "2026-11-08T01:00:00+00:00",
        "response_received_utc": "2026-11-08T01:00:02+00:00",
    }


class ResultPrivateArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = FakeGitHub()
        self.config = destination.configuration(ENV, required=True)

    def make_proof(self, event_id="2508371"):
        path = self.root / ("live-" + event_id)
        raw = original() if event_id == "2508371" else second()
        with patch("ops.sportsdb_event_capture._fetch",
                   return_value=(raw, receipt(event_id))):
            capture(path, event_id=event_id)
        return path, raw

    def upload(self, event_id="2508371", **kwargs):
        path, raw = self.make_proof(event_id)
        result = archive.archive(path, event_id=event_id,
                                 source_sha=SHA, run_id=RUN, attempt=ATTEMPT,
                                 config=self.config, opener=self.api, **kwargs)
        return result, raw

    def test_create_only_private_roundtrip_replays_original_bytes(self):
        result, raw = self.upload()
        self.assertEqual(result["archive_status"], "PRIVATE_REMOTE_READBACK_VERIFIED")
        self.assertTrue(result["private_storage_authenticated"])
        self.assertFalse(result["source_independence_authenticated"])
        self.assertFalse(result["independently_verified"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertIn(raw, self.api.archive)
        self.assertEqual(result["archive_sha256"],
                         hashlib.sha256(self.api.archive).hexdigest())
        self.assertNotIn(ENV["PRIVATE_ARCHIVE_REPOSITORY"], json.dumps(result))
        self.assertNotIn(TOKEN, json.dumps(result))
        puts = [req for req in self.api.calls if req.get_method() == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertNotIn("sha", json.loads(puts[0].data))  # create-only
        self.assertIn("/result-evidence/thesportsdb/v1/2508371/", puts[0].full_url)

    def test_second_event_uses_different_stable_namespace(self):
        result, raw = self.upload(event_id="2508372")
        self.assertIn(raw, self.api.archive)
        self.assertEqual(result["provider_event_id"], "2508372")
        puts = [req for req in self.api.calls if req.get_method() == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertIn("/result-evidence/thesportsdb/v1/2508372/", puts[0].full_url)

    def test_public_or_wrong_repository_rejected_before_write(self):
        for changes in (
            {"private": False, "visibility": "public"},
            {"visibility": "internal"},
            {"id": 999},
        ):
            with self.subTest(changes=changes):
                self.api = FakeGitHub()
                self.api.repo.update(changes)
                with self.assertRaises(destination.ArchiveError):
                    self.upload()
                self.assertIsNone(self.api.archive)

    def test_mutated_blob_fails_remote_readback(self):
        self.api.wrong_blob = True
        with self.assertRaises(archive.EvidenceArchiveError) as exc:
            self.upload()
        self.assertEqual(exc.exception.args[0],
                         "PRIVATE_EVIDENCE_READBACK_CHANGED")

    def test_forged_commit_reachability_fails(self):
        self.api.wrong_reachability = True
        with self.assertRaises(archive.EvidenceArchiveError) as exc:
            self.upload()
        self.assertEqual(exc.exception.args[0], "PRIVATE_EVIDENCE_REACHABILITY")

    def test_duplicate_destination_refuses_overwrite(self):
        self.upload()
        with self.assertRaises(destination.ArchiveError):
            self.upload()

    def test_offline_original_not_accepted_as_live(self):
        path = self.root / "offline"
        capture(path, raw=original())
        with self.assertRaises(CaptureError):
            archive.archive(path, event_id="2508371", source_sha=SHA,
                            run_id=RUN, attempt=ATTEMPT,
                            config=self.config, opener=self.api)
        self.assertEqual(self.api.calls, [])

    def test_wrong_event_id_cannot_reuse_other_raw(self):
        path, _ = self.make_proof()
        with self.assertRaises(CaptureError):
            archive.archive(path, event_id="2508372", source_sha=SHA,
                            run_id=RUN, attempt=ATTEMPT,
                            config=self.config, opener=self.api)
        self.assertEqual(self.api.calls, [])

    def test_missing_config_and_bad_context_do_not_call_network(self):
        path, _ = self.make_proof()
        with self.assertRaises(archive.EvidenceArchiveError):
            archive.archive(path, event_id="2508371", source_sha="bad",
                            run_id=RUN, attempt=ATTEMPT,
                            config=self.config, opener=self.api)
        with self.assertRaises(archive.EvidenceArchiveError):
            archive.archive(path, event_id="2508371", source_sha=SHA,
                            run_id=RUN, attempt=ATTEMPT,
                            config=None, opener=self.api)
        self.assertEqual(self.api.calls, [])

    def test_remote_visibility_change_blocks_success(self):
        self.api.public_on_read = 3
        with self.assertRaises(destination.ArchiveError):
            self.upload()


if __name__ == "__main__":
    unittest.main()
