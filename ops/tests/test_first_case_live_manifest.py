"""Private, create-only live manifest entrypoint: no synthetic case admission."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from first_case_live_manifest import build, create
from first_case_payload_binding import audit
from test_first_case_rfc3161_link import bundle, encoded

NOW = datetime(2026, 11, 21, 10, 2, tzinfo=timezone.utc)


def adjusted(f=None, q=None, **changes):
    raw_f, raw_q, _ = bundle()
    forecast = json.loads(raw_f) if f is None else f
    quote = json.loads(raw_q) if q is None else q
    forecast.update(changes.get("forecast", {}))
    quote.update(changes.get("quote", {}))
    return encoded(forecast), encoded(quote)


class FirstCaseLiveManifestTests(unittest.TestCase):
    def test_make_manifest_from_real_runtime_clock_value_and_raw_hashes(self):
        f, q = adjusted()
        raw, report = build(f, q, now=NOW)
        manifest = json.loads(raw)
        self.assertEqual(manifest["created_utc"], "2026-11-21T10:02:00Z")
        self.assertEqual(manifest["forecast_sha256"], hashlib.sha256(f).hexdigest())
        self.assertEqual(manifest["quote_sha256"], hashlib.sha256(q).hexdigest())
        self.assertEqual(audit(f, q, raw)["status"], "HOLD")
        self.assertTrue(report["byte_digest_binding_checked"])
        self.assertEqual(report["certified_forward_case_count"], 0)
        self.assertFalse(report["eligible_for_model_scoring"])
        self.assertEqual(report["production_recommendations"], "DISABLED")

    def test_local_now_does_not_accept_hour_old_observation_claims(self):
        f, q = adjusted()
        for when in (NOW + timedelta(seconds=1),
                     NOW + timedelta(minutes=10), NOW + timedelta(hours=3)):
            with self.subTest(now=when):
                with self.assertRaisesRegex(ValueError, "LIVE_QUOTE_NO_LONGER_FRESH|CHRONOLOGY_INVALID"):
                    build(f, q, now=when)

    def test_quote_was_fresh_when_captured_but_stale_when_manifest_created(self):
        f, q = adjusted(quote={
            "observed_utc": "2026-11-21T09:55:00Z",
            "captured_utc": "2026-11-21T09:55:20Z",
        })
        with self.assertRaisesRegex(ValueError, "LIVE_QUOTE_NO_LONGER_FRESH"):
            build(f, q, now=NOW)

    def test_backdated_forecast_disallowed_even_if_quote_is_fresh(self):
        f, q = adjusted(forecast={
            "captured_utc": "2026-11-21T09:30:00Z",
        }, quote={
            "observed_utc": "2026-11-21T09:29:00Z",
            "captured_utc": "2026-11-21T09:29:30Z",
        })
        with self.assertRaisesRegex(ValueError, "LIVE_QUOTE_NO_LONGER_FRESH"):
            build(f, q, now=NOW)

    def test_future_forged_clock_claim_rejected(self):
        f, q = adjusted(forecast={"captured_utc": "2026-11-21T10:10:00Z"})
        with self.assertRaisesRegex(ValueError, "CHRONOLOGY_INVALID"):
            build(f, q, now=NOW)

    def test_kickoff_buffer_10_minutes_or_less_rejected(self):
        for kickoff in ("2026-11-21T10:09:59Z", "2026-11-21T10:11:59Z"):
            f, q = adjusted(forecast={"kickoff_utc": kickoff},
                            quote={"kickoff_utc": kickoff})
            with self.assertRaisesRegex(ValueError, "CHRONOLOGY_INVALID"):
                build(f, q, now=NOW)

    def test_create_only_keeps_sources_bitwise_identical(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            f, q = adjusted()
            forecast, quote = folder/"forecast.json", folder/"quote.json"
            output = folder/"manifest.json"
            forecast.write_bytes(f)
            quote.write_bytes(q)
            result = create(forecast, quote, output, now=NOW)
            self.assertEqual(forecast.read_bytes(), f)
            self.assertEqual(quote.read_bytes(), q)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(),
                             result["manifest_sha256"])
            self.assertTrue(result["byte_digest_binding_checked"])
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(result["certified_forward_case_count"], 0)
            self.assertFalse(result["market_quote_executable_authenticated"])
            self.assertEqual(result["production_recommendations"], "DISABLED")
            if os.name == "posix":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "UNSAFE_OR_EXISTING_MANIFEST_OUTPUT"):
                create(forecast, quote, output, now=NOW)

    def test_input_and_output_path_swap_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            f, q = adjusted()
            forecast, quote = folder/"forecast.json", folder/"quote.json"
            forecast.write_bytes(f)
            quote.write_bytes(q)
            with self.assertRaisesRegex(ValueError, "UNSAFE_OR_EXISTING_MANIFEST_OUTPUT"):
                create(forecast, quote, forecast, now=NOW)
            link = folder/"link.json"
            link.symlink_to(forecast)
            with self.assertRaisesRegex(ValueError, "UNSAFE_OR_EXISTING_MANIFEST_OUTPUT"):
                create(forecast, quote, link, now=NOW)
            with self.assertRaisesRegex(ValueError, "UNSAFE_OR_OVERSIZED_EVIDENCE_FILE"):
                create(link, quote, folder/"manifest.json", now=NOW)
            self.assertFalse((folder/"manifest.json").exists())

    def test_bad_timestamp_production_flag_and_price_not_accepted(self):
        cases = [
            ({"captured_utc": "bad"}, {}),
            ({}, {"decimal_odds": True}),
            ({}, {"observed_utc": "bad"}),
            ({}, {"production_recommendations": "ENABLED"}),
        ]
        for fchange, qchange in cases:
            with self.subTest(fchange=fchange, qchange=qchange):
                f, q = adjusted(forecast=fchange, quote=qchange)
                with self.assertRaises(ValueError):
                    build(f, q, now=NOW)

    def test_must_have_timezone_aware_runtime_clock(self):
        f, q = adjusted()
        for clock in ("2026-11-21T10:02:00Z",
                      datetime(2026, 11, 21, 10, 2), True):
            with self.subTest(clock=clock):
                with self.assertRaisesRegex(ValueError, "INVALID_CAPTURE_CLOCK"):
                    build(f, q, now=clock)

    def test_no_file_created_if_sources_cannot_pass_live_checks(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            f, q = adjusted()
            first, second, target = (p/"f.json", p/"q.json", p/"manifest.json")
            first.write_bytes(f)
            second.write_bytes(q)
            with self.assertRaises(ValueError):
                create(first, second, target, now=NOW+timedelta(hours=1))
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
