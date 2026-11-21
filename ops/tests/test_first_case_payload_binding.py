"""Synthetic adversarial evidence-binding tests. No invented certified cases."""
import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from first_case_payload_binding import audit, inspect, main


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def fixtures():
    forecast = {
        "schema": "football-king-first-case-forecast-v1",
        "fixture_id": "synthetic-bundesliga-001",
        "league": "bundesliga",
        "home_key": "club-a", "away_key": "club-b",
        "kickoff_utc": "2026-11-21T12:00:00Z",
        "captured_utc": "2026-11-21T10:01:00Z",
        "model_version": "research-a",
        "probabilities_1x2": [.50, .25, .25],
        "production_recommendations": "DISABLED",
    }
    quote = {
        "schema": "football-king-first-case-quote-v1",
        "fixture_id": "synthetic-bundesliga-001",
        "league": "bundesliga",
        "home_key": "club-a", "away_key": "club-b",
        "kickoff_utc": "2026-11-21T12:00:00Z",
        "provider": "synthetic-provider",
        "provider_event_id": "provider-native-123",
        "market": "spreads",
        "selection": "HOME",
        "line": -.25,
        "observed_utc": "2026-11-21T10:00:00Z",
        "captured_utc": "2026-11-21T10:00:30Z",
        "decimal_odds": 1.943,
        "production_recommendations": "DISABLED",
    }
    return forecast, quote


def bundle(forecast=None, quote=None, manifest_override=None):
    if forecast is None or quote is None:
        initial_f, initial_q = fixtures()
        forecast = initial_f if forecast is None else forecast
        quote = initial_q if quote is None else quote
    forecast_raw, quote_raw = encoded(forecast), encoded(quote)
    manifest = {
        "schema": "football-king-first-case-manifest-v1",
        "fixture_id": forecast["fixture_id"],
        "kickoff_utc": forecast["kickoff_utc"],
        "forecast_sha256": hashlib.sha256(forecast_raw).hexdigest(),
        "quote_sha256": hashlib.sha256(quote_raw).hexdigest(),
        "created_utc": "2026-11-21T10:02:00Z",
        "status": "HOLD",
        "production_recommendations": "DISABLED",
    }
    if manifest_override:
        manifest.update(manifest_override)
    return forecast_raw, quote_raw, encoded(manifest)


class FirstCaseBindingTests(unittest.TestCase):
    def test_valid_claimed_byte_and_chronology_binding_still_hold(self):
        f, q, m = bundle()
        out = inspect(f, q, m)
        self.assertEqual(out["status"], "HOLD")
        self.assertTrue(out["byte_digest_binding_checked"])
        self.assertTrue(out["declared_prematch_time_order_checked"])
        self.assertEqual(out["forecast_sha256"], hashlib.sha256(f).hexdigest())
        self.assertEqual(out["quote_sha256"], hashlib.sha256(q).hexdigest())
        self.assertEqual(out["manifest_sha256"], hashlib.sha256(m).hexdigest())
        self.assertFalse(out["forecast_capture_time_independently_authenticated"])
        self.assertFalse(out["timestamp_token_verified_for_manifest_here"])
        self.assertFalse(out["regulation_ft_settlement_authenticated"])
        self.assertFalse(out["eligible_for_model_scoring"])
        self.assertFalse(out["positive_ev_verified"])
        self.assertEqual(out["certified_forward_case_count"], 0)
        self.assertEqual(out["production_recommendations"], "DISABLED")
        self.assertIsNone(out["recommended_stake"])
        self.assertNotIn("decimal_odds", out)
        self.assertNotIn("probabilities_1x2", out)

    def test_forecast_byte_rewrite_invalidates_manifest_pin(self):
        f, q, m = bundle()
        altered = f.replace(b"research-a", b"research-b")
        out = audit(altered, q, m)
        self.assertEqual(out["reason"], "RAW_BYTES_DIGEST_MISMATCH")
        self.assertFalse(out["byte_digest_binding_checked"])

    def test_market_quote_change_even_one_byte_invalidates_pin(self):
        f, q, m = bundle()
        new_quote = q.replace(b"1.943", b"1.944")
        self.assertEqual(audit(f, new_quote, m)["reason"], "RAW_BYTES_DIGEST_MISMATCH")

    def test_different_market_fixture_with_fresh_pins_is_rejected(self):
        f, q = fixtures()
        q["fixture_id"] = "swapped-event"
        out = audit(*bundle(f, q))
        self.assertEqual(out["reason"], "CROSS_SOURCE_IDENTITY_CLAIM_MISMATCH")

    def test_same_fixture_but_wrong_team_key_and_kickoff_hold(self):
        f, q = fixtures()
        q["away_key"] = "another-club"
        self.assertEqual(audit(*bundle(f, q))["reason"], "CROSS_SOURCE_IDENTITY_CLAIM_MISMATCH")
        f, q = fixtures()
        q["kickoff_utc"] = "2026-11-21T13:00:00Z"
        self.assertEqual(audit(*bundle(f, q))["reason"], "CROSS_SOURCE_KICKOFF_CLAIM_MISMATCH")

    def test_manifest_claims_prematch_when_actual_order_violates(self):
        f, q = fixtures()
        f["captured_utc"] = "2026-11-21T12:01:00Z"
        self.assertEqual(audit(*bundle(f, q))["reason"], "LOOKAHEAD_OR_INVALID_CAPTURE_ORDER")
        f, q = fixtures()
        q["observed_utc"] = "2026-11-21T10:04:00Z"
        self.assertEqual(audit(*bundle(f, q))["reason"], "LOOKAHEAD_OR_INVALID_CAPTURE_ORDER")
        f, q = fixtures()
        self.assertEqual(audit(*bundle(f, q, {
            "created_utc": "2026-11-21T11:55:00Z",
        }))["reason"], "LOOKAHEAD_OR_INVALID_CAPTURE_ORDER")

    def test_quote_age_must_be_at_most_120_seconds(self):
        f, q = fixtures()
        q["observed_utc"] = "2026-11-21T09:58:20Z"
        self.assertEqual(audit(*bundle(f, q))["reason"], "STALE_CLAIMED_QUOTE")
        f, q = fixtures()
        q["observed_utc"] = "2026-11-21T09:58:30Z"
        self.assertEqual(audit(*bundle(f, q))["reason"],
                         "QUOTE_STALE_AT_FORECAST_SEAL")
        f, q = fixtures()
        self.assertTrue(inspect(*bundle(f, q))["byte_digest_binding_checked"])

    def test_initially_fresh_quote_but_hour_late_forecast_seal_holds(self):
        f, q = fixtures()
        q["observed_utc"] = "2026-11-21T09:00:00Z"
        q["captured_utc"] = "2026-11-21T09:00:30Z"
        # Even though the quote was 30 seconds old when copied, it has
        # expired long before the original signed forecast and manifest.
        out = audit(*bundle(f, q))
        self.assertEqual(out["reason"], "QUOTE_STALE_AT_FORECAST_SEAL")
        self.assertFalse(out["byte_digest_binding_checked"])
        self.assertEqual(out["certified_forward_case_count"], 0)

    def test_uncertified_claim_flags_cannot_be_injected(self):
        f, q, m = bundle()
        for bad in ("independently_timestamped", "certified_case_count",
                    "market_quote_executable_authenticated"):
            decoded = json.loads(m)
            decoded[bad] = True
            out = audit(f, q, encoded(decoded))
            self.assertEqual(out["reason"], "INVALID_EVIDENCE_SCHEMA_OR_RELEASE_FLAG")

    def test_wrong_market_direction_or_fractional_line_rejected(self):
        for market, selection, line in (
            ("h2h", "HOME", 0), ("totals", "HOME", 2.75),
            ("spreads", "OVER", -.25), ("spreads", "HOME", -.3),
            ("totals", "OVER", 2.6), ("live", "HOME", 0),
        ):
            f, q = fixtures()
            q.update(market=market, selection=selection, line=line)
            self.assertIn(audit(*bundle(f, q))["reason"],
                          ("MARKET_DIRECTION_LINE_MISMATCH", "UNSUPPORTED_MARKET"))
        f, q = fixtures()
        q.update(market="h2h", selection="DRAW", line=None)
        self.assertTrue(inspect(*bundle(f, q))["byte_digest_binding_checked"])

    def test_duplicate_json_keys_nan_and_boolean_price_fail_closed(self):
        f, q, m = bundle()
        fraud = f[:-2] + b',"fixture_id":"override"}'
        self.assertEqual(audit(fraud, q, m)["reason"], "DUPLICATE_JSON_FIELD")
        for marker in (b'NaN', b'Infinity', b'true'):
            f, q, m = bundle()
            price = q.replace(b"1.943", marker)
            out = audit(price, q, m) if marker == b'true' else audit(f, price, m)
            self.assertEqual(out["status"], "HOLD")
            self.assertEqual(out["certified_forward_case_count"], 0)

    def test_synthetic_public_claim_never_becomes_one_certified_case(self):
        f, q, m = bundle()
        # Even a valid manifest, signed in a future independent stage, does
        # not prove original publisher FT results or a tradable market price.
        out = audit(f, q, m)
        self.assertEqual(out["certified_forward_case_count"], 0)
        self.assertEqual(out["production_recommendations"], "DISABLED")

    def test_cli_only_prints_safe_report_not_raw_quote(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw = bundle()
            for filename, payload in zip(("forecast.json", "quote.json", "manifest.json"), raw):
                (base/filename).write_bytes(payload)
            stdout = StringIO()
            with redirect_stdout(stdout):
                main(["--forecast", str(base/"forecast.json"),
                      "--quote", str(base/"quote.json"),
                      "--manifest", str(base/"manifest.json")])
            obj = json.loads(stdout.getvalue())
            self.assertTrue(obj["byte_digest_binding_checked"])
            self.assertNotIn("1.943", stdout.getvalue())
            self.assertEqual(obj["certified_forward_case_count"], 0)


if __name__ == "__main__":
    unittest.main()
