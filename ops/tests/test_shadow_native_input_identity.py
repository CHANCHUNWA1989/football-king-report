"""Same-response field retention; synthetic mutations never certify football facts."""
import copy
import functools
import gzip
import hashlib
import io
import json
import sys
import tarfile
import types
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shadow_forecast as forecast

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SHA256 = "12e46fb527c012598f76eadcae8b04c41bf20b9345920dd59cd3a2cd40af7c8e"
INPUT_FIELD = "native_fixture_input"
SOURCE_FIELD = "source_response_sha256"


class NativeInputIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = (ROOT / "packages/football_king_v4_1_iphone_verified.zip").read_bytes()
        if hashlib.sha256(package).hexdigest() != PACKAGE_SHA256:
            raise AssertionError("original package digest changed")
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            cls.gateway_source = archive.read("football_king_v4_1/fixture_gateway.py")
            cls.safety_source = archive.read("football_king_v4_1/fixture_safety.py")
        capture = ROOT / "openliga_capture_provenance/2026/11/04/41760476423-1/openliga-capture.tar.gz"
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(capture.read_bytes())), mode="r:") as archive:
            cls.original_body = archive.extractfile("openligadb.json").read()
        cls.original_rows = json.loads(cls.original_body)

    def setUp(self):
        self.now = datetime(2026, 11, 4, 14, 27, tzinfo=timezone.utc)
        self.calls = []
        self.body = self.original_body
        stub = types.ModuleType("openfootball")
        stub.fetch = lambda *args, **kwargs: {"status": "HOLD", "matches": []}
        safety = types.ModuleType("fixture_safety")
        exec(compile(self.safety_source, "original/fixture_safety.py", "exec"), safety.__dict__)
        self.gateway = types.ModuleType("fixture_gateway")
        self.modules = patch.dict(sys.modules, {"openfootball": stub, "fixture_safety": safety,
                                               "fixture_gateway": self.gateway})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        exec(compile(self.gateway_source, "original/fixture_gateway.py", "exec"), self.gateway.__dict__)
        self.original_fetch = self.gateway.fetch_openligadb
        # Keeps the pre-fix default getter offline too, for the red reproduction.
        self.gateway.fetch_openligadb = functools.partial(self.original_fetch, opener=self.opener)
        self.urlopen = patch.object(forecast, "urlopen", self.opener, create=True)
        self.urlopen.start()
        self.addCleanup(self.urlopen.stop)
        self.leagues = patch.object(forecast, "LEAGUES", ("bundesliga",))
        self.leagues.start()
        self.addCleanup(self.leagues.stop)

    def opener(self, request, timeout):
        self.calls.append((request.full_url, timeout))
        return io.BytesIO(self.body)

    def run_default(self, **kwargs):
        return forecast.generate(now=self.now, **kwargs)

    def target(self, report):
        return next(row for row in report["predictions"] if row["event_id"] == "openligadb:83234")

    def mutate_target(self, change):
        rows = copy.deepcopy(self.original_rows)
        selected = next(row for row in rows if row["matchID"] == 83234)
        change(selected, rows)
        self.body = json.dumps(rows, ensure_ascii=False).encode()

    def test_same_get_retains_existing_native_ids_and_response_digest(self):
        output = self.run_default()
        evidence = self.target(output)[INPUT_FIELD]
        self.assertEqual(evidence["schema"], "football-king-native-fixture-input-observation-v1")
        self.assertEqual(evidence["status"], "UNAUTHENTICATED")
        self.assertEqual((evidence["match_id"], evidence["home_team_id"], evidence["away_team_id"]),
                         (83234, 100, 87))
        self.assertEqual((evidence["league_shortcut"], evidence["league_season"]), ("bl1", 2026))
        digest = hashlib.sha256(self.body).hexdigest()
        self.assertEqual(evidence[SOURCE_FIELD], digest)
        self.assertEqual(output["sources"][0][SOURCE_FIELD], digest)
        self.assertEqual(self.calls, [("https://api.openligadb.de/getmatchdata/bl1/2026", 12)])
        for field in ("source_identity_authenticated", "source_capture_authenticated",
                      "raw_input_durably_archived", "native_ids_used_as_model_features",
                      "eligible_for_model_scoring"):
            self.assertIs(evidence[field], False)
        self.assertIs(evidence["native_ids_from_same_response_as_gateway_fixture"], True)
        self.assertEqual(output["production_recommendations"], "DISABLED")


    def test_closed_metadata_and_model_training_are_unchanged(self):
        baseline = self.run_default(getter=self.gateway.get_fixtures)
        updated = self.run_default()
        expected_fields = {"schema", "status", "provider", "match_id", "home_team_id",
                           "away_team_id", "league_id", "league_shortcut", "league_season",
                           SOURCE_FIELD, "native_ids_from_same_response_as_gateway_fixture",
                           "source_identity_authenticated", "source_capture_authenticated",
                           "raw_input_durably_archived", "native_ids_used_as_model_features",
                           "eligible_for_model_scoring"}
        native_count = 0
        for row in updated["predictions"]:
            if INPUT_FIELD in row:
                native_count += 1
                self.assertEqual(set(row[INPUT_FIELD]), expected_fields)
                row.pop(INPUT_FIELD)
        self.assertEqual(native_count, 18)
        updated["sources"][0].pop(SOURCE_FIELD)
        # Includes exact probabilities, goal rates, model ID, training count/digest,
        # times, source metadata, and the remainder of the forecast output.
        self.assertEqual(updated, baseline)
        self.assertEqual(len(self.calls), 2)  # one GET per independently run path

    def test_bad_missing_or_equal_native_team_ids_do_not_change_research(self):
        for bad in (None, True, False, 0, -1, 100.0, "100", 2**63, 87):
            with self.subTest(home_team_id=bad):
                self.mutate_target(lambda row, rows: row["team1"].update(teamId=bad))
                output = self.run_default()
                self.assertNotIn(INPUT_FIELD, self.target(output))
                self.assertEqual(output["production_recommendations"], "DISABLED")
        self.mutate_target(lambda row, rows: row["team1"].pop("teamId"))
        self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))

    def test_wrong_or_untyped_league_scope_has_no_identity_claim(self):
        for key, bad in (("leagueSeason", 2025), ("leagueSeason", True),
                         ("leagueSeason", "2026"), ("leagueShortcut", "bl2"),
                         ("leagueId", -1), ("leagueId", True), ("leagueId", 4938)):
            with self.subTest(key=key, value=bad):
                self.mutate_target(lambda row, rows: row.update({key: bad}))
                self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))
        self.mutate_target(lambda row, rows: row.pop("leagueSeason"))
        self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))

    def test_duplicate_native_match_is_not_resolved_by_row_order(self):
        for changed in (False, True):
            with self.subTest(conflicting_team_ids=changed):
                def duplicate(row, rows):
                    other = copy.deepcopy(row)
                    if changed:
                        other["team1"]["teamId"], other["team2"]["teamId"] = 87, 100
                    rows.append(other)
                self.mutate_target(duplicate)
                self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))

    def test_contradictory_native_team_bindings_in_same_response_are_rejected(self):
        def swapped_ids(row, rows):
            row["team1"]["teamId"], row["team2"]["teamId"] = 87, 100
        self.mutate_target(swapped_ids)
        self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))
        self.mutate_target(lambda row, rows: row["team1"].update(teamId=999999))
        self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))

    def test_swapped_normalized_home_away_does_not_gain_raw_identity(self):
        def swapped(*args, **kwargs):
            result = self.original_fetch(*args, **kwargs)
            row = next(r for r in result["matches"] if r["event_id"] == "openligadb:83234")
            row["home"], row["away"] = row["away"], row["home"]
            return result
        self.gateway.fetch_openligadb = swapped
        self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))

    def test_duplicate_json_keys_never_choose_a_native_identity(self):
        for original, replacement in (("\"teamId\": 100", "\"teamId\": 999999, \"teamId\": 100"),
                                      ("\"leagueSeason\": 2026", "\"leagueSeason\": 2025, \"leagueSeason\": 2026")):
            with self.subTest(duplicate=original):
                rows = copy.deepcopy(self.original_rows)
                selected = json.dumps(next(row for row in rows if row["matchID"] == 83234))
                self.body = json.dumps(rows).replace(selected, selected.replace(original, replacement, 1), 1).encode()
                # The frozen gateway accepts last-key-wins JSON; identity metadata must not.
                output = self.run_default()
                self.assertNotIn(INPUT_FIELD, self.target(output))
                self.assertEqual(output["sources"][0][SOURCE_FIELD], hashlib.sha256(self.body).hexdigest())

    def test_nonfinite_json_never_produces_native_identity(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=bad):
                self.mutate_target(lambda row, rows: row.update(unusedNativeField=bad))
                self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))
        for token in (b"1e9999", b"-1e9999"):
            with self.subTest(overflowing_json_number=token):
                self.mutate_target(lambda row, rows: row.update(unusedNativeField=None))
                self.body = self.body.replace(b'"unusedNativeField": null',
                                              b'"unusedNativeField": ' + token)
                self.assertNotIn(INPUT_FIELD, self.target(self.run_default()))

    def test_native_only_parser_recursion_failure_keeps_original_research_rows(self):
        result = self.original_fetch("2026-27", "bundesliga", opener=self.opener,
                                     clock=lambda: self.now)
        original_matches = copy.deepcopy(result["matches"])
        with patch.object(forecast.json, "loads", side_effect=RecursionError("raw data hidden")):
            returned = forecast._native_openliga_inputs(result, self.body,
                                                        season="2026-27", league="bundesliga")
        self.assertEqual(returned["matches"], original_matches)
        self.assertNotIn("raw data hidden", json.dumps(returned))

    def test_hash_mismatch_cannot_claim_same_response_evidence(self):
        def mismatched(*args, **kwargs):
            result = self.original_fetch(*args, **kwargs)
            result["sha256"] = "0" * 64
            return result
        self.gateway.fetch_openligadb = mismatched
        output = self.run_default()
        self.assertNotIn(INPUT_FIELD, self.target(output))
        self.assertNotIn(SOURCE_FIELD, output["sources"][0])

    def test_foreign_metadata_and_caller_verified_flags_are_not_copied(self):
        raw = self.original_fetch("2026-27", "bundesliga", opener=self.opener,
                                  clock=lambda: self.now)
        evil = {"schema": "football-king-native-fixture-input-observation-v1",
                "status": "VERIFIED", "verified": True, "eligible_for_model_scoring": True}
        for row in raw["matches"]:
            row[INPUT_FIELD] = evil
            row["_same_response_native_fixture_input"] = evil
        raw["_same_response_source_sha256"] = "a" * 64
        output = self.run_default(getter=lambda **kwargs: copy.deepcopy(raw))
        self.assertNotIn(INPUT_FIELD, self.target(output))
        self.assertNotIn(SOURCE_FIELD, output["sources"][0])
        direct = forecast.predict_league(raw["matches"], "bundesliga", self.now)
        self.assertTrue(direct)
        self.assertTrue(all(INPUT_FIELD not in row for row in direct))

    def test_response_whitespace_matches_original_normalizer_without_id_guessing(self):
        self.mutate_target(lambda row, rows: row["team1"].update(teamName="  Hamburger SV  "))
        self.assertEqual(self.target(self.run_default())[INPUT_FIELD]["home_team_id"], 100)

    def test_original_body_read_bound_and_single_get_survive_oversize(self):
        self.body = b" " * 8_000_001
        read_sizes = []
        class RecordedBody(io.BytesIO):
            def read(self, size=-1):
                read_sizes.append(size)
                return super().read(size)
        def opener(request, timeout):
            self.calls.append((request.full_url, timeout))
            return RecordedBody(self.body)
        with patch.object(forecast, "urlopen", opener):
            output = self.run_default()
        self.assertEqual(read_sizes, [8_000_001])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(output["status"], "HOLD")
        self.assertNotIn(SOURCE_FIELD, output["sources"][0])

    def test_capture_failure_keeps_existing_fallback_without_exposing_raw_errors(self):
        def failed(request, timeout):
            self.calls.append((request.full_url, timeout))
            raise OSError("arbitrary raw upstream body must stay private")
        with patch.object(forecast, "urlopen", failed):
            output = self.run_default()
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(output["status"], "HOLD")
        self.assertNotIn("arbitrary raw", json.dumps(output))
        self.assertNotIn(SOURCE_FIELD, output["sources"][0])

    def test_large_native_catalogue_skips_metadata_without_dropping_forecasts(self):
        rows = copy.deepcopy(self.original_rows)
        rows.extend(copy.deepcopy(rows[-1]) for _ in range(1301-len(rows)))
        self.body = json.dumps(rows).encode()
        output = self.run_default()
        self.assertNotIn(INPUT_FIELD, self.target(output))
        self.assertTrue(output["predictions"])
        self.assertEqual(output["sources"][0][SOURCE_FIELD], hashlib.sha256(self.body).hexdigest())

    def test_default_live_completion_still_excludes_target_inside_ten_minutes(self):
        started = self.now
        completed = started + timedelta(seconds=61)
        kickoff = started + timedelta(minutes=11)
        self.mutate_target(lambda row, rows: row.update(matchDateTimeUTC=kickoff.isoformat()))
        class AdvancingDatetime(datetime):
            current = started
            @classmethod
            def now(cls, tz=None):
                return cls.current.astimezone(tz or timezone.utc)
        class SlowBody(io.BytesIO):
            def read(self, size=-1):
                data = super().read(size)
                AdvancingDatetime.current = completed
                return data
        def opener(request, timeout):
            self.calls.append((request.full_url, timeout))
            return SlowBody(self.body)
        with patch.object(forecast, "datetime", AdvancingDatetime), \
                patch.object(forecast, "urlopen", opener):
            output = forecast.generate()
        self.assertEqual(output["as_of_utc"], completed.isoformat())
        self.assertFalse(any(r["event_id"] == "openligadb:83234" for r in output["predictions"]))
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(output["predictions"])
        for row in output["predictions"]:
            self.assertEqual(row["prediction_utc"], completed.isoformat())
            if INPUT_FIELD in row:
                self.assertNotIn("captured_utc", row[INPUT_FIELD])


if __name__ == "__main__":
    unittest.main()
