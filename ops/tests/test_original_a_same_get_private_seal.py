"""Synthetic no-network tests of the original A one-GET raw private seam."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from ops import shadow_forecast
from ops.original_a_same_get_private_seal import (
    MAX_BODY, _private_directory, check_private_bundle, seal,
)

SHA = hashlib.sha256
NOW = datetime(2026, 11, 15, 13, tzinfo=timezone.utc)


def original(body=b'[{"matchID":7}]'):
    return {
        "status": "READY_RESEARCH", "source": "OpenLigaDB",
        "league": "bundesliga", "season": "2026-27",
        "sha256": SHA(body).hexdigest(),
        "_same_response_source_sha256": SHA(body).hexdigest(),
        "captured_utc": (NOW - timedelta(minutes=1)).isoformat(),
    }


class SourcePrivateSealTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.body = b'[{"matchID":7,"team1":{"teamId":5}}]'

    def save(self, *, body=None, src=None):
        return seal(self.dir, body=self.body if body is None else body,
                    original=original(self.body) if src is None else src,
                    season="2026-27", league="bundesliga", now=NOW)

    def path(self, report):
        return self.dir / (report["private_bundle_sha256_unattested"] +
                           ".openliga-private.tar")

    def test_exact_one_original_body_preserved_and_replayed(self):
        report = self.save()
        self.assertEqual(report["status"], "HOLD")
        self.assertTrue(report["local_raw_bytes_saved"])
        self.assertFalse(report["external_timestamp_attested"])
        self.assertFalse(report["publisher_identity_authenticated"])
        self.assertEqual(report["certified_prospective_samples"], 0)
        self.assertFalse(report["positive_ev_verified"])
        path = self.path(report)
        self.assertTrue(path.is_file())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual([p.name for p in self.dir.iterdir()],
                         [path.name])
        checked = check_private_bundle(
            path, expected_bundle_sha256=report["private_bundle_sha256_unattested"],
            expected_raw_sha256=SHA(self.body).hexdigest())
        self.assertTrue(checked["exact_same_get_bytes_locally_replayed"])
        self.assertFalse(checked["independent_capture_time_verified"])
        self.assertFalse(checked["publisher_identity_authenticated"])

    def test_identical_attempt_must_not_overwrite(self):
        result = self.save()
        original_bytes = self.path(result).read_bytes()
        with self.assertRaises(FileExistsError):
            self.save()
        self.assertEqual(self.path(result).read_bytes(), original_bytes)
        self.assertEqual(len(list(self.dir.iterdir())), 1)

    def test_modified_raw_body_with_stale_gateway_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, "ORIGINAL_GATEWAY_RESPONSE_HASH_MISMATCH"):
            self.save(body=self.body + b"x")
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_false_source_sha_field_rejected(self):
        source = original(self.body)
        source["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.save(src=source)
        self.assertFalse(list(self.dir.iterdir()))

    def test_forged_same_get_receipt_rejected(self):
        source = original(self.body)
        del source["_same_response_source_sha256"]
        with self.assertRaises(ValueError):
            self.save(src=source)

    def test_future_gateway_capture_claim_rejected(self):
        source = original(self.body)
        source["captured_utc"] = (NOW + timedelta(seconds=1)).isoformat()
        with self.assertRaises(ValueError):
            self.save(src=source)
        self.assertFalse(list(self.dir.iterdir()))

    def test_non_aware_gateway_capture_rejected(self):
        source = original(self.body)
        source["captured_utc"] = "2026-11-15T12:59:00"
        with self.assertRaises(ValueError):
            self.save(src=source)

    def test_source_identity_must_be_exact_openligadb_bundesliga(self):
        for field,value in (("source", "OtherSource"), ("league", "epl"),
                            ("season", "2025-26"), ("status", "HOLD")):
            with self.subTest(field=field):
                source = original(self.body)
                source[field] = value
                with self.assertRaises(ValueError):
                    self.save(src=source)

    def test_oversized_body_rejected_without_writing(self):
        body = b"x" * (MAX_BODY + 1)
        with self.assertRaises(ValueError):
            self.save(body=body)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_empty_body_rejected(self):
        with self.assertRaises(ValueError):
            self.save(body=b"")

    def test_world_readable_private_directory_rejected(self):
        self.dir.chmod(0o755)
        with self.assertRaisesRegex(ValueError, "UNSAFE_PRIVATE_CAPTURE_DIRECTORY"):
            self.save()

    def test_missing_private_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNAVAILABLE_PRIVATE_CAPTURE_DIRECTORY"):
            seal(self.dir / "missing", body=self.body, original=original(self.body),
                 season="2026-27", league="bundesliga", now=NOW)

    def test_relative_capture_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNSAFE_PRIVATE_CAPTURE_DIRECTORY"):
            seal(Path("private"), body=self.body, original=original(self.body),
                 season="2026-27", league="bundesliga", now=NOW)

    def test_capture_symlink_directory_rejected(self):
        alias = self.dir.parent / (self.dir.name + "-alias")
        alias.symlink_to(self.dir, target_is_directory=True)
        self.addCleanup(alias.unlink)
        with self.assertRaises(ValueError):
            seal(alias, body=self.body, original=original(self.body),
                 season="2026-27", league="bundesliga", now=NOW)

    def test_tampered_existing_bundle_fails_replay(self):
        report = self.save()
        path = self.path(report)
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "PRIVATE_CAPTURE_BUNDLE_HASH_MISMATCH"):
            check_private_bundle(path, expected_bundle_sha256=
                                 report["private_bundle_sha256_unattested"],
                                 expected_raw_sha256=SHA(self.body).hexdigest())

    def test_forged_expected_raw_digest_fails_replay(self):
        report = self.save()
        with self.assertRaises(ValueError):
            check_private_bundle(self.path(report),
                expected_bundle_sha256=report["private_bundle_sha256_unattested"],
                expected_raw_sha256="a" * 64)

    def test_hardlinked_private_bundle_rejected(self):
        report = self.save()
        alias = self.dir / "alias"
        os.link(self.path(report), alias)
        with self.assertRaises(ValueError):
            check_private_bundle(self.path(report),
                expected_bundle_sha256=report["private_bundle_sha256_unattested"],
                expected_raw_sha256=SHA(self.body).hexdigest())

    def test_local_wall_clock_must_be_aware(self):
        with self.assertRaises(ValueError):
            seal(self.dir, body=self.body, original=original(self.body),
                 season="2026-27", league="bundesliga",
                 now=datetime(2026, 11, 15, 13))


class ShadowSameOriginalGETTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def install_fake_gateway(self):
        now = datetime.now(timezone.utc)
        hk = now.astimezone(shadow_forecast.HK)
        year = hk.year if hk.month >= 7 else hk.year - 1
        ko = now + timedelta(hours=5)
        row = {
            "matchID": 123456, "leagueShortcut": "bl1",
            "leagueSeason": year, "leagueId": 100,
            "matchDateTimeUTC": ko.isoformat(),
            "team1": {"teamId": 41, "teamName": "Alpha"},
            "team2": {"teamId": 42, "teamName": "Beta"},
            "matchIsFinished": False,
            "matchResults": [],
        }
        raw = json.dumps([row], separators=(",", ":")).encode()
        calls = []

        def open_url(request, timeout):
            calls.append("one-GET")
            return io.BytesIO(raw)

        def get_fixtures(*, season, league, clock, openligadb_fn):
            if league != "bundesliga":
                return {"status": "HOLD", "reason": "SYNTHETIC_OTHER_LEAGUE_NOT_USED"}
            return openligadb_fn(season, league, clock=clock)

        def fetch_openligadb(season, league, *, opener, clock):
            with opener("https://api.openligadb.de/getmatchdata/bl1/"+str(year),
                        timeout=4) as response:
                body = response.read(8_000_001)
            return {
                "status": "READY_RESEARCH", "source": "OpenLigaDB",
                "source_url": "https://api.openligadb.de/getmatchdata/bl1/"+str(year),
                "season": season, "league": league,
                "sha256": SHA(body).hexdigest(),
                "captured_utc": clock().isoformat(),
                "matches": [{
                    "status": "SCHEDULED", "event_id": "openligadb:123456",
                    "home": "Alpha", "away": "Beta", "kickoff_utc": ko.isoformat(),
                    "date": ko.date().isoformat(),
                }],
            }

        def predict(data, league, at):
            if league != "bundesliga":
                return []
            p = data[0]
            return [{
                "league": league, "event_id": p["event_id"],
                "home": p["home"], "away": p["away"],
                "kickoff_utc": p["kickoff_utc"],
                "prediction_utc": at.isoformat(),
                "model": "poisson-shrinkage-unvalidated-v4.1",
                "p_home": .5, "p_draw": .3, "p_away": .2,
                "calibrated": False,
                "verified_market_odds": False,
                "production_recommendations": "DISABLED",
            }]
        gateway = types.SimpleNamespace(get_fixtures=get_fixtures,
                                        fetch_openligadb=fetch_openligadb)
        return raw, calls, gateway, open_url, predict

    def test_explicit_optin_preserves_original_normalizer_input_one_request(self):
        raw, calls, gateway, opener, predict = self.install_fake_gateway()
        with patch.dict(sys.modules, {"fixture_gateway": gateway}), patch.object(
                shadow_forecast, "urlopen", side_effect=opener), patch.object(
                shadow_forecast, "predict_league", side_effect=predict):
            output = shadow_forecast.generate(raw_capture_dir=str(self.directory))
        self.assertEqual(calls, ["one-GET"])
        self.assertEqual(output["predictions_count"], 1)
        self.assertEqual(output["production_recommendations"], "DISABLED")
        a = output["predictions"][0]
        self.assertEqual(a["native_fixture_input"]["home_team_id"], 41)
        self.assertEqual(a["native_fixture_input"]["source_response_sha256"],
                         SHA(raw).hexdigest())
        self.assertFalse(a["native_fixture_input"]["raw_input_durably_archived"])
        src = next(x for x in output["sources"] if x["league"] == "bundesliga")
        self.assertEqual(src["source_response_sha256"], SHA(raw).hexdigest())
        self.assertEqual(src["private_same_get_raw_sha256_unattested"],
                         SHA(raw).hexdigest())
        self.assertFalse(src["private_source_capture_independently_attested"])
        private_sha = src["private_same_get_bundle_sha256_unattested"]
        actual = check_private_bundle(
            self.directory / (private_sha + ".openliga-private.tar"),
            expected_bundle_sha256=private_sha,
            expected_raw_sha256=SHA(raw).hexdigest())
        self.assertTrue(actual["exact_same_get_bytes_locally_replayed"])
        self.assertFalse(actual["publisher_identity_authenticated"])

    def test_default_no_raw_capture_no_extra_http_get(self):
        raw, calls, gateway, opener, predict = self.install_fake_gateway()
        with patch.dict(sys.modules, {"fixture_gateway": gateway}), patch.object(
                shadow_forecast, "urlopen", side_effect=opener), patch.object(
                shadow_forecast, "predict_league", side_effect=predict):
            output = shadow_forecast.generate()
        self.assertEqual(calls, ["one-GET"])
        src = next(x for x in output["sources"] if x["league"] == "bundesliga")
        self.assertNotIn("private_same_get_raw_sha256_unattested", src)
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_replay_with_raw_capture_disabled_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "PRIVATE_SOURCE_CAPTURE_REQUIRES_LIVE_NATIVE_GETTER"):
            shadow_forecast.generate(
                now=NOW, raw_capture_dir=str(self.directory))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_custom_getter_cannot_spoof_same_get(self):
        with self.assertRaisesRegex(ValueError, "PRIVATE_SOURCE_CAPTURE_REQUIRES_LIVE_NATIVE_GETTER"):
            shadow_forecast.generate(
                getter=lambda **kwargs: {"status": "READY_RESEARCH", "matches": []},
                raw_capture_dir=str(self.directory))
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_private_capture_failure_fails_closed_for_bundesliga(self):
        raw, calls, gateway, opener, predict = self.install_fake_gateway()
        self.directory.chmod(0o755)
        with patch.dict(sys.modules, {"fixture_gateway": gateway}), patch.object(
                shadow_forecast, "urlopen", side_effect=opener), patch.object(
                shadow_forecast, "predict_league", side_effect=predict):
            with self.assertRaises(ValueError):
                shadow_forecast.generate(raw_capture_dir=str(self.directory))
        self.assertEqual(calls, [])
        self.assertEqual(list(self.directory.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
