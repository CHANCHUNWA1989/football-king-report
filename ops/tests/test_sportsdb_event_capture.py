"""Offline security/identity regression for one isolated provider raw observation."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from ops.sportsdb_event_capture import capture, inspect, CaptureError, EVENT_ID, URL


def original(**changes):
    event = {"idEvent": EVENT_ID, "idLeague": "4331", "strSport": "Soccer",
             "strSeason": "2026-2027", "strHomeTeam": "Borussia Dortmund",
             "strAwayTeam": "Werder Bremen", "idHomeTeam": "1100",
             "idAwayTeam": "1200", "strTimestamp": "2026-10-09T18:30:00",
             "strStatus": "Match Finished", "intHomeScore": "2",
             "intAwayScore": "2"}
    event.update(changes)
    return json.dumps({"events": [event]}).encode()


class SportsDbCaptureTest(unittest.TestCase):
    def test_private_raw_and_receipt_local_offline_only(self):
        with TemporaryDirectory() as root:
            folder = Path(root) / "capture"
            receipt = capture(folder, raw=original(), now=datetime(2026, 11, 8, tzinfo=timezone.utc))
            self.assertEqual(receipt["source_observation"]["provider_score_claim"], [2, 2])
            self.assertEqual(receipt["source_observation"]["provider_event_id"], EVENT_ID)
            self.assertEqual(receipt["capture_mode"], "OFFLINE_TEST_ONLY")
            self.assertEqual(receipt["fixed_api_url"], URL)
            self.assertIsNone(receipt["http_status"])
            self.assertIsNone(receipt["http_final_url"])
            self.assertIsNone(receipt["http_content_type"])
            self.assertIsNone(receipt["http_redirects_followed"])
            self.assertIsNone(receipt["request_started_utc"])
            self.assertIsNone(receipt["response_received_utc"])
            self.assertFalse(receipt["independently_verified"])
            self.assertFalse(receipt["eligible_for_model_scoring"])
            self.assertEqual(receipt["production_recommendations"], "DISABLED")
            self.assertEqual((folder / "sportsdb-event.json").read_bytes(), original())
            self.assertEqual(json.loads((folder / "manifest.json").read_text()), receipt)
            self.assertEqual(os.stat(folder).st_mode & 0o777, 0o700)
            self.assertEqual(os.stat(folder / "sportsdb-event.json").st_mode & 0o777, 0o600)
            with self.assertRaises(CaptureError) as exc:
                capture(folder, raw=original())
            self.assertEqual(exc.exception.code, "OUTPUT_ALREADY_EXISTS")

    def test_event_identity_is_pinned(self):
        for delta in ({"idEvent": "2508372"}, {"idLeague": "4328"},
                      {"strSport": "Basketball"}, {"strSeason": "2025-2026"},
                      {"strHomeTeam": "Other"}, {"strAwayTeam": "Other"},
                      {"idHomeTeam": "0"}, {"idAwayTeam": "1100"}):
            with self.subTest(delta=delta):
                with self.assertRaises(CaptureError) as exc:
                    inspect(original(**delta))
                self.assertEqual(exc.exception.code, "EVENT_IDENTITY_MISMATCH")

    def test_kickoff_must_match_original_record(self):
        for delta in ("2026-10-09T19:30:00", "2026-10-10T18:30:00", "invalid", None):
            with self.subTest(delta=delta):
                with self.assertRaises(CaptureError) as exc:
                    inspect(original(strTimestamp=delta))
                self.assertEqual(exc.exception.code, "EVENT_KICKOFF_MISMATCH")

    def test_status_and_score_not_inferred(self):
        for delta in ({"strStatus": "1st Half"}, {"intHomeScore": None},
                      {"intAwayScore": "3.0"}, {"intHomeScore": 31},
                      {"strStatus": "After Extra Time"}):
            with self.subTest(delta=delta):
                with self.assertRaises(CaptureError) as exc:
                    inspect(original(**delta))
                self.assertEqual(exc.exception.code, "EVENT_STATUS_OR_SCORE_UNSUPPORTED")

    def test_multiple_or_missing_events_fail(self):
        for body in ({"events": []}, {"events": [json.loads(original())["events"][0]] * 2},
                     {"events": None}, {}, []):
            with self.subTest(body=body):
                with self.assertRaises(CaptureError):
                    inspect(json.dumps(body).encode())

    def test_untrusted_json_fails_closed(self):
        for body in (b'{}', b'{"events": 1}', b'{"events": [], "events": []}',
                     b'{"events": NaN}', b'x', b'\xff', b'', b' ' * 512001):
            with self.subTest(raw=body[:20]):
                with self.assertRaises(CaptureError):
                    inspect(body)

    def test_failure_does_not_create_partial_files(self):
        with TemporaryDirectory() as root:
            target = Path(root) / "capture"
            with self.assertRaises(CaptureError):
                capture(target, raw=original(strStatus="Scheduled"))
            self.assertFalse(target.exists())

    def test_symlink_directory_is_rejected(self):
        with TemporaryDirectory() as root:
            path = Path(root)
            folder = path / "private"
            folder.mkdir()
            (path / "link").symlink_to(folder, target_is_directory=True)
            with self.assertRaises(CaptureError) as exc:
                capture(path / "link" / "capture", raw=original())
            self.assertEqual(exc.exception.code, "OUTPUT_ALREADY_EXISTS")

    def test_bad_clock_is_rejected(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(CaptureError) as exc:
                capture(Path(root) / "capture", raw=original(), now=datetime(2026, 11, 8))
            self.assertEqual(exc.exception.code, "BAD_CAPTURE_CLOCK")


    def test_public_repository_capture_path_is_rejected(self):
        checkout = Path(__file__).resolve().parents[2]
        target = checkout / "never-create-public-sportsdb-raw"
        self.assertFalse(target.exists())
        with self.assertRaises(CaptureError) as exc:
            capture(target, raw=original())
        self.assertEqual(exc.exception.code, "UNSAFE_OUTPUT_PATH")
        self.assertFalse(target.exists())

    def test_live_http_receipt_is_not_fabricated(self):
        with TemporaryDirectory() as root:
            receipt = {
                "http_status": 200, "http_final_url": URL,
                "http_content_type": "application/json",
                "http_redirects_followed": False,
                "request_started_utc": "2026-11-08T01:00:00+00:00",
                "response_received_utc": "2026-11-08T01:00:02+00:00",
            }
            with patch("ops.sportsdb_event_capture._fetch",
                       return_value=(original(), receipt)) as mock_fetch:
                result = capture(Path(root) / "capture")
            mock_fetch.assert_called_once_with()
            self.assertEqual(result["capture_mode"], "LIVE_API")
            self.assertEqual(result["http_status"], 200)
            self.assertEqual(result["http_final_url"], URL)
            self.assertEqual(result["request_started_utc"],
                             receipt["request_started_utc"])
            self.assertEqual(result["observed_utc"], receipt["response_received_utc"])
            self.assertFalse(result["independently_verified"])

    def test_live_caller_cannot_spoof_network_capture_clock(self):
        with TemporaryDirectory() as root:
            with self.assertRaises(CaptureError) as exc:
                capture(Path(root) / "capture",
                        now=datetime(2026, 11, 8, tzinfo=timezone.utc))
            self.assertEqual(exc.exception.code, "BAD_CAPTURE_CLOCK")

if __name__ == "__main__":
    unittest.main()
