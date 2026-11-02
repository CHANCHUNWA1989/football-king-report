"""Prospective model-score sealing is private, offline, and never an attested win."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from private_quote_snapshot_receipt import create_receipt
from private_quote_forward_freeze import (
    FreezeError, freeze, verify_freeze, main,
)

CAPTURE = "2026-11-02T05:00:00Z"
CODE = "a" * 40


def inputs():
    # Fully synthetic, never a real/authorized provider observation.
    fixture = {
        "provider_event_id": "private-native-event-1",
        "sport_key": "soccer_epl", "home_team": "Private Home",
        "away_team": "Private Away", "kickoff_utc": "2026-11-02T08:00:00Z"}
    market = {"market_type": "totals", "goals_line": 2.75}
    data = [{
        "id": fixture["provider_event_id"], "sport_key": fixture["sport_key"],
        "home_team": fixture["home_team"], "away_team": fixture["away_team"],
        "commence_time": fixture["kickoff_utc"],
        "bookmakers": [{
            "key": "synthetic-private-book",
            "markets": [{
                "key": "totals", "last_update": "2026-11-02T04:59:30Z",
                "outcomes": [
                    {"name": "Over", "point": 2.75, "price": 1.9183},
                    {"name": "Under", "point": 2.75, "price": 1.9587}
                ]}]
        }]
    }]
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    receipt = create_receipt(raw, CAPTURE)
    forecast = {
        "schema": "football-king-private-scoreline-forecast-v1",
        "provider_event_id": fixture["provider_event_id"],
        "market_type": "totals", "market_line_quarter_units": 11,
        "model_version": "research-v1",
        "model_code_commit": CODE,
        "training_cutoff_utc": "2026-11-01T00:00:00Z",
        "prediction_utc": "2026-11-02T05:01:00Z",
        "raw_snapshot_sha256": receipt["raw_response_sha256"],
        "quote_receipt_sha256_unanchored": receipt["receipt_sha256_unanchored"],
        "score_distribution": [[0, 0, .35], [1, 1, .40], [3, 1, .25]],
        "production_recommendations": "DISABLED",
    }
    return raw, receipt, fixture, market, forecast


def encode(forecast):
    return json.dumps(forecast, separators=(",", ":"), allow_nan=True).encode("utf-8")


class PrivateProspectiveFreezeTests(unittest.TestCase):
    def test_complete_private_chain_seals_model_bytes_without_publishing_odds(self):
        raw, receipt, fixture, market, prediction = inputs()
        seal = freeze(raw, receipt, fixture, market, encode(prediction))
        self.assertEqual(seal["status"], "RESEARCH_ONLY")
        self.assertEqual(seal["eligible_independently_verified_forward_samples"], 0)
        self.assertTrue(seal["exact_fixture_and_line_structurally_matched"])
        self.assertFalse(seal["forecast_was_witnessed_before_kickoff"])
        self.assertFalse(seal["training_data_leakage_independently_audited"])
        self.assertFalse(seal["eligible_for_model_scoring"])
        self.assertFalse(seal["can_publish_pick"])
        self.assertEqual(seal["production_recommendations"], "DISABLED")
        dumped = json.dumps(seal)
        for hidden in ("private-native-event-1", "Private Home", "Private Away",
                       "synthetic-private-book", "1.9183", "1.9587",
                       "research-v1", "score_distribution", '[[0,0,0.35]'):
            self.assertNotIn(hidden, dumped)

    def test_integrity_replay_is_not_external_signed_witness(self):
        raw, receipt, fixture, market, prediction = inputs()
        blob = encode(prediction)
        seal = freeze(raw, receipt, fixture, market, blob)
        replay = verify_freeze(raw, receipt, fixture, market, blob, seal)
        self.assertTrue(replay["local_bytes_and_semantics_replayed"])
        self.assertFalse(replay["independently_witnessed_before_kickoff"])
        self.assertEqual(replay["independent_forward_samples_credited"], 0)
        self.assertEqual(replay["status"], "HOLD")

    def test_single_raw_forecast_byte_change_rejected(self):
        raw, receipt, fixture, market, prediction = inputs()
        blob = encode(prediction)
        seal = freeze(raw, receipt, fixture, market, blob)
        for modified in (blob + b" ", blob.replace(b"0.35", b"0.36")):
            with self.assertRaisesRegex(FreezeError, "FORECAST_BYTES_CHANGED"):
                verify_freeze(raw, receipt, fixture, market, modified, seal)

    def test_forged_witness_and_sample_counter_cannot_replay(self):
        raw, receipt, fixture, market, prediction = inputs()
        blob = encode(prediction)
        sealed = freeze(raw, receipt, fixture, market, blob)
        for field, value in (
            ("forecast_was_witnessed_before_kickoff", True),
            ("eligible_independently_verified_forward_samples", 1000),
            ("can_publish_pick", True),
            ("production_recommendations", "ENABLED"),
            ("score_distribution_calibration_verified", True),
            ("raw_snapshot_sha256", "0"*64),
            ("training_cutoff_utc_claimed", "2027-01-01T00:00:00Z"),
        ):
            with self.subTest(field=field):
                forged = dict(sealed, **{field: value})
                with self.assertRaisesRegex(FreezeError, "SEAL_REPLAY_MISMATCH"):
                    verify_freeze(raw, receipt, fixture, market, blob, forged)
        forged = dict(sealed, "fabricated_certificate", True)
        with self.assertRaises(FreezeError):
            verify_freeze(raw, receipt, fixture, market, blob, forged)

    def test_reject_wrong_event_market_snapshot_and_model_commit(self):
        for field, value in (
            ("provider_event_id", "other-match"),
            ("market_type", "spreads"),
            ("market_line_quarter_units", 10),
            ("market_line_quarter_units", True),
            ("raw_snapshot_sha256", "0"*64),
            ("quote_receipt_sha256_unanchored", "0"*64),
            ("model_code_commit", "z"*40),
            ("production_recommendations", "ENABLED"),
        ):
            with self.subTest(field=field):
                raw, receipt, fixture, market, prediction = inputs()
                prediction[field] = value
                with self.assertRaises(FreezeError):
                    freeze(raw, receipt, fixture, market, encode(prediction))

    def test_reject_backdated_or_post_kickoff_forecast_clock(self):
        for field, value in (
            ("prediction_utc", "2026-11-02T04:59:59Z"),
            ("prediction_utc", "2026-11-02T07:50:00Z"),
            ("prediction_utc", "2026-11-02T08:00:00Z"),
            ("prediction_utc", "2026-11-02T05:01:00"),
            ("training_cutoff_utc", "2026-11-02T05:01:01Z"),
            ("training_cutoff_utc", "not-a-time"),
        ):
            with self.subTest(field=field, value=value):
                raw, receipt, fixture, market, prediction = inputs()
                prediction[field] = value
                with self.assertRaises(FreezeError):
                    freeze(raw, receipt, fixture, market, encode(prediction))

    def test_equivalent_timezone_allowed_but_microsecond_after_boundary_rejected(self):
        raw, receipt, fixture, market, prediction = inputs()
        prediction["prediction_utc"] = "2026-11-02T13:01:00+08:00"
        seal = freeze(raw, receipt, fixture, market, encode(prediction))
        self.assertEqual(seal["prediction_utc_claimed"], "2026-11-02T05:01:00+00:00")
        prediction["prediction_utc"] = "2026-11-02T07:50:00.000001Z"
        with self.assertRaisesRegex(FreezeError, "NON_PROSPECTIVE_FORECAST_CLOCK"):
            freeze(raw, receipt, fixture, market, encode(prediction))

    def test_duplicate_scoreline_nan_boolean_negative_and_nonunit_sum(self):
        cases = (
            [[0,0,.5],[0,0,.5]],
            [[0,0,.6],[0,1,.3]],
            [[0,0,True],[0,1,0]],
            [[0,0,float("nan")]],
            [[0,0,-.1],[1,0,1.1]],
            [[13,0,1.0]],
            [[-1,0,1.0]],
            [[0,0,1.0], [1,2,0.5]],
            [["0",0,1.0]],
            [[0,0,0.4],[1,0,float("inf")]],
            [[0,0,1.0], [0,1,0]],
        )
        for scorelines in cases[:-1]:
            with self.subTest(scorelines=str(scorelines)):
                raw, receipt, fixture, market, prediction = inputs()
                prediction["score_distribution"] = scorelines
                with self.assertRaises(FreezeError):
                    freeze(raw, receipt, fixture, market, encode(prediction))
        # A genuine zero-mass *distinct* scoreline is permitted.
        raw, receipt, fixture, market, prediction = inputs()
        prediction["score_distribution"] = cases[-1]
        self.assertEqual(freeze(raw, receipt, fixture, market, encode(prediction))["status"],
                         "RESEARCH_ONLY")

    def test_missing_provider_line_and_forged_local_quote_receipt_block(self):
        raw, receipt, fixture, market, forecast = inputs()
        bad_receipt = dict(receipt, publisher_independently_authenticated=True)
        with self.assertRaisesRegex(FreezeError, "UNVERIFIED_QUOTE_FIXTURE_BINDING"):
            freeze(raw, bad_receipt, fixture, market, encode(forecast))
        with self.assertRaisesRegex(FreezeError, "UNVERIFIED_QUOTE_FIXTURE_BINDING"):
            freeze(raw + b" ", receipt, fixture, market, encode(forecast))
        changed_market = {"market_type": "totals", "goals_line": 2.5}
        with self.assertRaisesRegex(FreezeError, "NO_ATOMIC_PREMATCH_MARKET_LINE"):
            freeze(raw, receipt, fixture, changed_market, encode(forecast))
        bad_fixture = dict(fixture, provider_event_id="other-event")
        with self.assertRaisesRegex(FreezeError, "UNVERIFIED_QUOTE_FIXTURE_BINDING"):
            freeze(raw, receipt, bad_fixture, market, encode(forecast))

    def test_forecast_contains_no_game_result_or_self_signed_credentials(self):
        for field, value in (
            ("settled_home_goals", 2), ("realized_roi", .3),
            ("independently_verified", True), ("bookmaker_prices", [1.93]),
            ("sigstore_bundle", "pretend"), ("recommendation", "OVER"),
        ):
            with self.subTest(field=field):
                raw, receipt, fixture, market, forecast = inputs()
                forecast[field] = value
                with self.assertRaisesRegex(FreezeError, "INVALID_FORECAST_SCHEMA"):
                    freeze(raw, receipt, fixture, market, encode(forecast))

    def test_cli_owner_only_exclusive_new_and_offline_replay(self):
        raw, receipt, fixture, market, forecast = inputs()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            docs={"odds.json":raw,
                  "receipt.json":json.dumps(receipt).encode(),
                  "fixture.json":json.dumps(fixture).encode(),
                  "market.json":json.dumps(market).encode(),
                  "forecast.json":encode(forecast)}
            for name, data in docs.items():
                (root/name).write_bytes(data)
            common=["--raw-odds",str(root/"odds.json"),
                    "--receipt",str(root/"receipt.json"),
                    "--fixture",str(root/"fixture.json"),
                    "--market",str(root/"market.json"),
                    "--forecast",str(root/"forecast.json")]
            with redirect_stdout(io.StringIO()) as output:
                code=main(common+["--output",str(root/"seal.json")])
            self.assertEqual(code,0)
            self.assertEqual(stat.S_IMODE((root/"seal.json").stat().st_mode),0o600)
            self.assertNotIn("synthetic-private-book",output.getvalue())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(common+["--verify-seal",str(root/"seal.json"),
                                         "--output",str(root/"replay.json")]),0)
            self.assertEqual(stat.S_IMODE((root/"replay.json").stat().st_mode),0o600)
            self.assertEqual(json.loads((root/"replay.json").read_text())[
                "independent_forward_samples_credited"],0)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(common+["--output",str(root/"seal.json")]),1)

    def test_untrusted_malformed_json_duplicate_keys_rejected(self):
        raw, receipt, fixture, market, forecast = inputs()
        for payload in (b'{"schema":"a","schema":"b"}',
                        b'{"schema":NaN}',
                        b'[]',
                        b'\xff',
                        b'{}',
                        b' ' * 64_001):
            with self.subTest(raw=payload[:40]):
                with self.assertRaises(FreezeError):
                    freeze(raw, receipt, fixture, market, payload)


if __name__ == "__main__":
    unittest.main()
