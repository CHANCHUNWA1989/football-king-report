"""Adversarial real private-pack replay tests; only synthetic provider bodies."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from first_case_private_quote_link import build, create
from test_first_case_rfc3161_link import bundle, encoded
from ops import private_response_capture as capture
from first_case_payload_binding import inspect

NOW = datetime(2026, 11, 21, 10, 2, tzinfo=timezone.utc)
CTX = dict(source_sha="a"*40, run_id="101", attempt="1")
PARAMS = {"regions":"eu","markets":"h2h","oddsFormat":"decimal","dateFormat":"iso"}


def market():
    return {
        "key": "h2h", "last_update": "2026-11-21T10:00:00Z",
        "outcomes": [
            {"name": "synthetic-home", "price": 1.96},
            {"name": "Draw", "price": 3.25},
            {"name": "synthetic-away", "price": 4.20},
        ],
    }


def event():
    return {
        "id": "synthetic-fixture-1",
        "sport_key": "soccer_germany_bundesliga",
        "home_team": "synthetic-home", "away_team": "synthetic-away",
        "commence_time": "2026-11-21T12:00:00Z",
        "bookmakers": [{"key": "betfair", "markets": [market()]}],
    }


def record(event_items=None, *, endpoint="/sports/soccer_germany_bundesliga/odds/"):
    return {
        "receipt": {"endpoint_path": endpoint,
                    "requested_utc": "2026-11-21T10:00:10Z",
                    "completed_utc": "2026-11-21T10:00:30Z"},
        "raw": encoded([event()] if event_items is None else event_items),
    }


class PrivateFirstCaseH2HTests(unittest.TestCase):
    def setUp(self):
        self.forecast = bundle()[0]
        self.pin = "a"*64

    def invoke(self, records=None, *, bookmaker_id="betfair", selection="HOME", now=NOW):
        return build(
            self.forecast, [record()] if records is None else records,
            pack_sha256=self.pin, bookmaker_id=bookmaker_id,
            selection=selection, now=now)

    def test_exact_native_one_response_quote_and_manifest_still_hold(self):
        quote, manifest, report = self.invoke()
        parsed = json.loads(quote)
        self.assertEqual(parsed["fixture_id"], "synthetic-fixture-1")
        self.assertEqual(parsed["provider_event_id"], "synthetic-fixture-1")
        self.assertEqual(parsed["provider"],
                         "the_odds_api_v4/betfair/"+self.pin)
        self.assertEqual(parsed["market"], "h2h")
        self.assertEqual(parsed["selection"], "HOME")
        self.assertIsNone(parsed["line"])
        self.assertEqual(parsed["decimal_odds"], 1.96)
        self.assertEqual(parsed["observed_utc"], "2026-11-21T10:00:00Z")
        self.assertEqual(parsed["captured_utc"], "2026-11-21T10:00:30Z")
        preflight = inspect(self.forecast, quote, manifest)
        self.assertTrue(preflight["byte_digest_binding_checked"])
        self.assertEqual(preflight["certified_forward_case_count"], 0)
        self.assertEqual(json.loads(manifest)["quote_sha256"],
                         hashlib.sha256(quote).hexdigest())
        self.assertFalse(report["original_capture_pin_replayed"])  # direct records
        self.assertFalse(report["bookmaker_quote_executable_authenticated"])
        self.assertFalse(report["source_native_id_independently_authenticated"])
        self.assertFalse(report["eligible_for_model_scoring"])
        self.assertEqual(report["production_recommendations"], "DISABLED")
        self.assertNotIn("decimal_odds", report)
        self.assertNotIn("probabilities_1x2", report)

    def test_unique_draw_side(self):
        quote, _, report = self.invoke(selection="DRAW")
        self.assertEqual(json.loads(quote)["decimal_odds"], 3.25)
        self.assertEqual(json.loads(quote)["selection"], "DRAW")
        self.assertEqual(report["certified_forward_case_count"], 0)

    def test_missing_duplicate_or_wrong_native_event_id(self):
        for events in ([], [event(), event()]):
            with self.subTest(events=len(events)), self.assertRaisesRegex(
                    ValueError, "NATIVE_EVENT_MISSING_OR_DUPLICATE_ACROSS_PACK"):
                self.invoke([record(events)])
        with self.assertRaisesRegex(ValueError, "NATIVE_EVENT_MISSING_OR_DUPLICATE_ACROSS_PACK"):
            self.invoke([record(), record()])
        alternate = event()
        alternate["id"] = "different-id"
        with self.assertRaisesRegex(ValueError, "NATIVE_EVENT_MISSING_OR_DUPLICATE_ACROSS_PACK"):
            self.invoke([record([alternate])])

    def test_conflicting_home_away_kickoff_and_wrong_league(self):
        for change in (
            {"home_team": "WRONG"}, {"away_team": "WRONG"},
            {"commence_time": "2026-11-21T12:01:00Z"},
            {"sport_key": "soccer_epl"},
            {"completed": True}, {"is_outright": True},
        ):
            e = event()
            e.update(change)
            with self.subTest(change=change), self.assertRaisesRegex(
                    ValueError, "NATIVE_EVENT_TEAM_KICKOFF_OR_PHASE_MISMATCH"):
                self.invoke([record([e])])
        with self.assertRaisesRegex(ValueError, "WRONG_PROVIDER_SPORT_SCOPE"):
            self.invoke([record(endpoint="/sports/soccer_epl/odds/")])

    def test_poisoned_bookmaker_or_h2h_market_quarantined(self):
        trials = [
            ("BOOKMAKER_MISSING_OR_DUPLICATE", lambda e: e["bookmakers"].append(
                copy.deepcopy(e["bookmakers"][0]))),
            ("H2H_MARKET_MISSING_OR_DUPLICATE", lambda e: e["bookmakers"][0]["markets"].append(
                copy.deepcopy(e["bookmakers"][0]["markets"][0]))),
            ("INCOMPLETE_OR_DUPLICATE_H2H_SIDES", lambda e: e["bookmakers"][0]["markets"][0]["outcomes"].pop()),
            ("INCOMPLETE_OR_DUPLICATE_H2H_SIDES", lambda e: e["bookmakers"][0]["markets"][0]["outcomes"][2].update(
                name="Draw")),
            ("INVALID_H2H_LINE", lambda e: e["bookmakers"][0]["markets"][0]["outcomes"][0].update(
                point=0.5)),
            ("INVALID_H2H_PRICE", lambda e: e["bookmakers"][0]["markets"][0]["outcomes"][0].update(
                price=True)),
            ("INVALID_MARKET_PHASE", lambda e: e["bookmakers"][0]["markets"][0].update(
                suspended_at="2026-11-21T10:00:00Z")),
        ]
        for err, mutate in trials:
            e = event()
            mutate(e)
            with self.subTest(error=err), self.assertRaisesRegex(ValueError, err):
                self.invoke([record([e])])

    def test_stale_quote_and_postforecast_capture_rejected(self):
        e = event()
        e["bookmakers"][0]["markets"][0]["last_update"] = "2026-11-21T09:59:59Z"
        with self.assertRaisesRegex(ValueError, "LIVE_QUOTE_OR_FORECAST_NOT_SEALABLE"):
            self.invoke([record([e])])
        r = record()
        r["receipt"]["completed_utc"] = "2026-11-21T10:01:30Z"
        with self.assertRaisesRegex(ValueError, "CAPTURE_OR_MARKET_CLOCK_CONFLICT"):
            self.invoke([r])

    def test_missing_bookmaker_wrong_selection_and_non_h2h_refused(self):
        with self.assertRaisesRegex(ValueError, "BOOKMAKER_MISSING_OR_DUPLICATE"):
            self.invoke(bookmaker_id="missing")
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_H2H_SELECTION"):
            self.invoke(selection="OVER")
        with self.assertRaisesRegex(ValueError, "INVALID_BOOKMAKER_SELECTION"):
            self.invoke(bookmaker_id="betfair;secret")
        e = event()
        e["bookmakers"][0]["markets"] = [{"key":"spreads"}]
        with self.assertRaisesRegex(ValueError, "H2H_MARKET_MISSING_OR_DUPLICATE"):
            self.invoke([record([e])])

    def test_actual_private_pack_replay_and_create_only_file_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private_capture = root/"pack"
            outputs = root/"output"
            outputs.mkdir(mode=0o700)
            forecast = outputs/"forecast.json"
            forecast.write_bytes(self.forecast)
            os.chmod(forecast, 0o600)
            with capture.CaptureSession(private_capture, **CTX) as s:
                s.record(encoded([event()]),
                         path="/sports/soccer_germany_bundesliga/odds/",
                         params=PARAMS, secret="NOT_IN_PROVIDER_BODY",
                         quota={"used":1,"remaining":490,"last":1},
                         requested=datetime(2026,11,21,10,0,10,tzinfo=timezone.utc),
                         completed=datetime(2026,11,21,10,0,30,tzinfo=timezone.utc))
                pack = s.seal()
            report = create(
                private_capture, forecast, **CTX,
                expected_manifest_sha256=pack["manifest_sha256"],
                bookmaker_id="betfair", selection="HOME",
                quote_output=outputs/"quote.json",
                manifest_output=outputs/"manifest.json", now=NOW)
            self.assertTrue(report["original_capture_pin_replayed"])
            self.assertTrue(report["exact_native_id_team_kickoff_matched"])
            self.assertEqual(report["certified_forward_case_count"], 0)
            self.assertEqual(report["status"], "HOLD")
            self.assertTrue((outputs/"manifest.json").exists())
            self.assertEqual(forecast.read_bytes(), self.forecast)
            self.assertEqual((outputs/"quote.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "OUTPUT_EXISTS_OR_UNSAFE"):
                create(private_capture, forecast, **CTX,
                       expected_manifest_sha256=pack["manifest_sha256"],
                       bookmaker_id="betfair", selection="HOME",
                       quote_output=outputs/"quote.json",
                       manifest_output=outputs/"manifest.json", now=NOW)
            # Caller cannot exchange a different real pack digest after replay.
            (outputs/"quote.json").unlink()
            (outputs/"manifest.json").unlink()
            with self.assertRaisesRegex(ValueError, "PRIVATE_MANIFEST_PIN_MISMATCH"):
                create(private_capture, forecast, **CTX,
                       expected_manifest_sha256="0"*64, bookmaker_id="betfair",
                       selection="HOME", quote_output=outputs/"quote.json",
                       manifest_output=outputs/"manifest.json", now=NOW)
            self.assertFalse((outputs/"quote.json").exists())


if __name__ == "__main__":
    unittest.main()
