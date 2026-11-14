"""No network calls: private two-source fixture crosswalk synthetic regressions."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_private_quote_forward_freeze import inputs, encode
from private_quote_forward_freeze import freeze
from private_kickoff_crosswalk_gate import (
    CrosswalkError, crosscheck, main,
)


def sample():
    raw, receipt, fixture, market, forecast = inputs()
    blob = encode(forecast)
    seal = freeze(raw, receipt, fixture, market, blob)
    def source(namespace, source_id, updated="2026-11-02T04:59:00Z",
               captured="2026-11-02T05:00:00Z"):
        rows = [{
            "id": source_id, "sport_key": fixture["sport_key"],
            "home_team": fixture["home_team"], "away_team": fixture["away_team"],
            "commence_time": fixture["kickoff_utc"],
            "last_update": updated, "status": "SCHEDULED",
        }]
        return {"provider_namespace": namespace, "source_event_id": source_id,
                "captured_utc": captured,
                "snapshot_bytes": json.dumps(rows, separators=(",", ":")).encode()}
    src_a = source("openligadb", "OLDB-1")
    src_b = source("openfootball", "OPEN-900", "2026-11-02T04:58:45Z")
    return raw, receipt, fixture, market, blob, seal, [src_a, src_b]


def check(case):
    return crosscheck(*case[:6], case[6])


def source_rows(source):
    return json.loads(source["snapshot_bytes"])


def put_rows(source, rows):
    source["snapshot_bytes"] = json.dumps(rows, separators=(",", ":")).encode()


class TwoSourceKickoffCrosswalkTests(unittest.TestCase):
    def test_exact_crosswalk_from_two_different_sources(self):
        result = check(sample())
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertTrue(result["private_forecast_seal_replayed"])
        self.assertTrue(result["home_and_away_orientation_exactly_matched"])
        self.assertTrue(result["kickoff_instant_exactly_agreed"])
        self.assertTrue(result["both_schedule_event_ids_unique_in_their_snapshots"])
        self.assertTrue(result["two_nonidentical_local_schedule_snapshots"])
        self.assertFalse(result["source_raw_payloads_independently_authenticated"])
        self.assertFalse(result["publisher_independence_independently_verified"])
        self.assertFalse(result["schedule_captured_clocks_independently_attested"])
        self.assertFalse(result["source_fixture_id_crosswalk_independently_authenticated"])
        self.assertFalse(result["actual_kickoff_independently_confirmed"])
        self.assertFalse(result["eligible_for_model_scoring"])
        self.assertFalse(result["eligible_for_betting_promotion"])
        self.assertEqual(result["certified_independent_forward_samples"], 0)
        self.assertEqual(result["production_recommendations"], "DISABLED")
        safe = json.dumps(result)
        for private in ("Private Home", "Private Away", "OLDB-1", "OPEN-900",
                        "openligadb", "openfootball", "1.9183", "1.9587",
                        "2026-11-02T08:00:00"):
            self.assertNotIn(private, safe)

    def test_timezone_equivalent_exact_instants_pass(self):
        case = list(sample())
        rows = source_rows(case[6][1])
        rows[0]["commence_time"] = "2026-11-02T16:00:00+08:00"
        put_rows(case[6][1], rows)
        self.assertTrue(check(case)["kickoff_instant_exactly_agreed"])

    def test_even_one_second_kickoff_conflict_quarantines(self):
        case = list(sample())
        rows = source_rows(case[6][1])
        rows[0]["commence_time"] = "2026-11-02T08:00:01Z"
        put_rows(case[6][1], rows)
        with self.assertRaisesRegex(CrosswalkError, "CONFLICTING_KICKOFF_INSTANT"):
            check(case)

    def test_swapped_home_away_and_wrong_sport_rejected(self):
        for field, val in (("home_team", "Private Away"),
                           ("away_team", "Private Home"),
                           ("sport_key", "soccer_spain_la_liga")):
            with self.subTest(field=field):
                case = list(sample())
                rows = source_rows(case[6][1])
                rows[0][field] = val
                put_rows(case[6][1], rows)
                with self.assertRaisesRegex(CrosswalkError, "SCHEDULE_FIXTURE_IDENTITY_CONFLICT"):
                    check(case)

    def test_explicit_crosswalk_id_required_and_unique_in_each_snapshot(self):
        for mutation in ("wrong", "duplicated", "same-fixture-second-id"):
            with self.subTest(mutation=mutation):
                case = list(sample())
                if mutation == "wrong":
                    case[6][1]["source_event_id"] = "wrong-id"
                    code = "MISSING_OR_DUPLICATED_SCHEDULE_EVENT_ID"
                else:
                    rows = source_rows(case[6][1])
                    duplicate = deepcopy(rows[0])
                    if mutation == "same-fixture-second-id":
                        duplicate["id"] = "other-ID"
                        code = "AMBIGUOUS_SAME_FIXTURE_IN_SNAPSHOT"
                    else:
                        code = "MISSING_OR_DUPLICATED_SCHEDULE_EVENT_ID"
                    rows.append(duplicate)
                    put_rows(case[6][1], rows)
                with self.assertRaisesRegex(CrosswalkError, code):
                    check(case)

    def test_same_publisher_or_odds_vendor_is_not_independent(self):
        case = list(sample())
        case[6][1]["provider_namespace"] = "openligadb"
        with self.assertRaisesRegex(CrosswalkError, "DUPLICATED_SCHEDULE_PUBLISHER_NAMESPACE"):
            check(case)
        case = list(sample())
        case[6][1]["provider_namespace"] = "the_odds_api_v4"
        with self.assertRaisesRegex(CrosswalkError, "INVALID_SOURCE_IDENTITY"):
            check(case)

    def test_identical_snapshots_cannot_be_counted_as_two_sources(self):
        case = list(sample())
        case[6][1]["snapshot_bytes"] = case[6][0]["snapshot_bytes"]
        case[6][1]["source_event_id"] = case[6][0]["source_event_id"]
        with self.assertRaisesRegex(CrosswalkError, "IDENTICAL_SCHEDULE_SNAPSHOTS"):
            check(case)

    def test_semantically_identical_snapshot_with_new_json_spacing_rejected(self):
        case = list(sample())
        # Same publisher row disguised under another namespace and formatting.
        case[6][1]["snapshot_bytes"] = json.dumps(
            source_rows(case[6][0]), indent=4, sort_keys=True).encode()
        case[6][1]["source_event_id"] = case[6][0]["source_event_id"]
        with self.assertRaisesRegex(CrosswalkError, "IDENTICAL_SCHEDULE_SNAPSHOTS"):
            check(case)

    def test_naive_kickoff_or_unhashable_status_rejected_as_safe_code(self):
        for field, value in (
            ("commence_time", "2026-11-02T08:00:00"),
            ("last_update", "2026-11-02T04:59:00"),
            ("status", ["SCHEDULED"]),
        ):
            with self.subTest(field=field):
                case = list(sample())
                rows = source_rows(case[6][1])
                rows[0][field] = value
                put_rows(case[6][1], rows)
                with self.assertRaises(CrosswalkError):
                    check(case)

    def test_nonprematch_results_or_cancelled_matches_rejected(self):
        for status in ("FINISHED", "IN_PLAY", "CANCELLED", "POSTPONED", None):
            with self.subTest(status=status):
                case = list(sample())
                rows = source_rows(case[6][1])
                rows[0]["status"] = status
                put_rows(case[6][1], rows)
                with self.assertRaisesRegex(CrosswalkError, "UNCONFIRMED_SCHEDULE_STATUS"):
                    check(case)

    def test_schedule_source_timestamp_must_precede_capture_and_prediction(self):
        for label, captured, last_update in (
            ("postprediction", "2026-11-02T05:02:00Z", "2026-11-02T04:59:00Z"),
            ("stale", "2026-11-01T22:00:00Z", "2026-11-01T21:59:00Z"),
            ("postcaptureupdate", "2026-11-02T05:00:00Z", "2026-11-02T05:00:01Z"),
            ("naive", "2026-11-02T05:00:00", "2026-11-02T04:59:00Z"),
        ):
            with self.subTest(label=label):
                case = list(sample())
                case[6][1]["captured_utc"] = captured
                rows = source_rows(case[6][1])
                rows[0]["last_update"] = last_update
                put_rows(case[6][1], rows)
                with self.assertRaises(CrosswalkError):
                    check(case)

    def test_unknown_or_duplicate_json_values_rejected(self):
        case = list(sample())
        for snap in (b'[{"id":"a","id":"b"}]', b'[{"x":NaN}]',
                     b"{}", b"[]", b'\xff',
                     b'[{"id": 1}]', b"x" * 1_000_001):
            with self.subTest(first=snap[:10]):
                copy = deepcopy(case)
                copy[6][1]["snapshot_bytes"] = snap
                with self.assertRaises(CrosswalkError):
                    check(copy)

    def test_missing_second_source_or_bogus_schema_rejected(self):
        case = list(sample())
        for sources in ([], [case[6][0]], case[6] + [case[6][0]], None):
            with self.subTest(size=len(sources) if sources else None):
                with self.assertRaisesRegex(CrosswalkError, "TWO_SCHEDULE_SOURCES_REQUIRED"):
                    crosscheck(*case[:6], sources)
        case = list(sample())
        rows = source_rows(case[6][1])
        rows[0]["price"] = 1.91
        put_rows(case[6][1], rows)
        with self.assertRaisesRegex(CrosswalkError, "INVALID_SCHEDULE_EVENT_SCHEMA"):
            check(case)

    def test_bad_forecast_seal_or_quote_does_not_reach_schedule_comparison(self):
        case = list(sample())
        case[5] = dict(case[5], forecast_was_witnessed_before_kickoff=True)
        with self.assertRaisesRegex(CrosswalkError, "UNVERIFIED_PRIVATE_PREDICTION_SEAL"):
            check(case)
        case = list(sample())
        case[0] += b" "
        with self.assertRaisesRegex(CrosswalkError, "UNVERIFIED_PRIVATE_PREDICTION_SEAL"):
            check(case)

    def test_private_cli_output_owner_only_no_override(self):
        raw, receipt, fixture, market, forecast, seal, sources = sample()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blobs = {"odds.json": raw, "receipt.json": json.dumps(receipt).encode(),
                     "fixture.json": json.dumps(fixture).encode(),
                     "market.json": json.dumps(market).encode(),
                     "forecast.json": forecast, "seal.json": json.dumps(seal).encode(),
                     "s-a.json": sources[0]["snapshot_bytes"],
                     "s-b.json": sources[1]["snapshot_bytes"]}
            for filename, value in blobs.items():
                (root/filename).write_bytes(value)
            argv = []
            for param, filename in (("raw-odds", "odds.json"), ("receipt", "receipt.json"),
                                    ("fixture", "fixture.json"), ("market", "market.json"),
                                    ("forecast", "forecast.json"), ("seal", "seal.json"),
                                    ("source-a", "s-a.json"), ("source-b", "s-b.json")):
                argv += ["--" + param, str(root/filename)]
            for i, prefix in enumerate(("source-a", "source-b")):
                argv += ["--"+prefix+"-name", sources[i]["provider_namespace"],
                         "--"+prefix+"-id", sources[i]["source_event_id"],
                         "--"+prefix+"-captured-utc", sources[i]["captured_utc"]]
            argv += ["--output", str(root/"audit.json")]
            with redirect_stdout(io.StringIO()) as out:
                self.assertEqual(main(argv), 0, out.getvalue())
            parsed = json.loads((root/"audit.json").read_text())
            self.assertFalse(parsed["actual_kickoff_independently_confirmed"])
            self.assertEqual(stat.S_IMODE((root/"audit.json").stat().st_mode), 0o600)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv), 1)
            self.assertTrue((root/"audit.json").exists())


if __name__ == "__main__":
    unittest.main()
