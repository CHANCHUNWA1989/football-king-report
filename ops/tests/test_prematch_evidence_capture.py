import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ops import prematch_evidence_capture as capture_module
from ops.prematch_evidence_capture import capture_pre_match
from ops.tests.test_frozen_forecast_join import sample
from ops.tests.test_bookmaker_timestamp_gate import fixture
from ops.prospective_evidence_chain import canonical_record_sha256


def metadata():
    return {
        "event_id": "e-1", "provider_event_id": "p-1",
        "model_version": "v1", "market": "h2h", "bookmaker": "example",
        "forecast_source_commit": "abcdef123",
        "forecast_captured_utc": "2026-11-06T08:00:00Z",
        "odds_captured_utc": "2026-11-06T09:00:00Z",
        "kickoff_utc": "2026-11-06T12:00:00Z",
    }


class PrematchCaptureTests(unittest.TestCase):
    def test_result_not_required_or_stored(self):
        result = capture_pre_match(metadata(), b"f", b"o", b"m")
        self.assertEqual(result["outcome_status"], "NOT_YET_SETTLED")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertNotIn("result_payload_sha256", result["record"])
        self.assertFalse(result["source_independently_attested"])

    def test_future_forecast_rejected(self):
        m = metadata()
        m["forecast_captured_utc"] = "2026-11-06T13:00:00Z"
        with self.assertRaises(ValueError):
            capture_pre_match(m, b"f", b"o", b"m")

    def test_future_odds_rejected(self):
        m = metadata()
        m["odds_captured_utc"] = "2026-11-06T13:00:00Z"
        with self.assertRaises(ValueError):
            capture_pre_match(m, b"f", b"o", b"m")

    def test_missing_identity_rejected(self):
        m = metadata()
        m.pop("provider_event_id")
        with self.assertRaises(ValueError):
            capture_pre_match(m, b"f", b"o", b"m")

    def test_digest_changes_when_quote_changes(self):
        a = capture_pre_match(metadata(), b"f", b"o", b"m")
        b = capture_pre_match(metadata(), b"f", b"o2", b"m")
        self.assertNotEqual(a["record_sha256"], b["record_sha256"])


def pipeline_inputs():
    """Synthetic contracts only; no real quotes or profitability evidence."""
    _, forecasts, _ = sample()
    model = b"synthetic model artifact"
    forecasts[0]["model_artifact_sha256"] = hashlib.sha256(model).hexdigest()
    m = dict(metadata(), event_id="synthetic-1", provider_event_id="synthetic-1",
             model_version="test", market="total", bookmaker="synthetic_book",
             forecast_captured_utc="2026-11-06T11:00:00Z",
             odds_captured_utc="2026-11-06T12:01:00Z",
             kickoff_utc="2026-11-06T13:00:00Z",
             source_provider="the_odds_api",
             source_url="https://api.the-odds-api.com/v4/historical/sports/test/odds",
             license_reference="synthetic-test-only")
    return m, json.dumps(forecasts).encode(), json.dumps(fixture()).encode(), model


class MarketInputCaptureTests(unittest.TestCase):
    def capture(self, inputs):
        return capture_module.capture_market_inputs(*inputs)

    def test_same_native_id_from_another_provider_does_not_mask_valid_capture(self):
        inputs = list(pipeline_inputs())
        forecasts = json.loads(inputs[1])
        foreign = dict(forecasts[0], event_source="provider-b", model_version="other-match")
        inputs[1] = json.dumps([foreign, *forecasts]).encode()
        result = self.capture(inputs)
        self.assertEqual(result["record"]["quotes"][0]["event_source"], "the_odds_api_v4")
        self.assertEqual(result["record"]["quotes"][0]["model_version"], "test")
        self.assertFalse(result["record"]["quotes"][0]["positive_ev_verified"])

    def test_binds_raw_quotes_forecast_model_and_times_without_results(self):
        inputs = pipeline_inputs()
        result = self.capture(inputs)
        record = result["record"]
        quote, = record["quotes"]
        self.assertEqual((quote["event_id"], quote["odds"], quote["line"]),
                         ("synthetic-1", "1.91", "2.5"))
        self.assertEqual(quote["forecast_created_at"], "2026-11-06T11:00:00Z")
        self.assertEqual(quote["captured_at"], "2026-11-06T12:00:00Z")
        self.assertEqual(record["odds_captured_utc"], "2026-11-06T12:01:00Z")
        self.assertEqual(quote["market_last_update"], "2026-11-06T11:58:00Z")
        self.assertEqual(record["odds_payload_sha256"], hashlib.sha256(inputs[2]).hexdigest())
        self.assertEqual(record["forecast_payload_sha256"], hashlib.sha256(inputs[1]).hexdigest())
        self.assertEqual(record["model_sha256"], quote["model_artifact_sha256"])
        self.assertEqual(result["record_sha256"], canonical_record_sha256(record))
        self.assertEqual(result["outcome_status"], "NOT_YET_SETTLED")
        self.assertNotIn("home_goals", quote)
        self.assertFalse(quote["positive_ev_verified"])
        self.assertFalse(result["source_independently_attested"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_missing_or_unsafe_source_rejected(self):
        for field in ("source_provider", "source_url", "license_reference"):
            inputs = list(pipeline_inputs())
            del inputs[0][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.capture(inputs)
        inputs = list(pipeline_inputs())
        inputs[0]["source_url"] += "?apiKey=synthetic-secret"
        with self.assertRaises(ValueError):
            self.capture(inputs)

    def test_current_public_consensus_is_not_a_raw_odds_source(self):
        inputs = list(pipeline_inputs())
        inputs[2] = (Path(__file__).resolve().parents[2] / "market/latest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "raw bookmaker"):
            self.capture(inputs)

    def test_model_artifact_mismatch_rejected(self):
        inputs = list(pipeline_inputs())
        inputs[3] += b" changed"
        with self.assertRaises(ValueError):
            self.capture(inputs)

    def test_provider_decimal_price_text_is_not_rounded(self):
        inputs = list(pipeline_inputs())
        inputs[2] = inputs[2].replace(b'1.91', b'1.9100000000000000001')
        self.assertEqual(self.capture(inputs)["record"]["quotes"][0]["odds"],
                         "1.9100000000000000001")

    def test_explicit_frozen_kickoff_conflict_rejected(self):
        inputs = list(pipeline_inputs())
        forecasts = json.loads(inputs[1])
        forecasts[0]["kickoff_at"] = "2026-11-06T14:00:00Z"
        inputs[1] = json.dumps(forecasts).encode()
        with self.assertRaises(ValueError):
            self.capture(inputs)

    def test_reuses_existing_handicap_identity_gate(self):
        inputs = list(pipeline_inputs())
        inputs[0]["market"] = "handicap"
        envelope = json.loads(inputs[2])
        event = envelope["data"][0]
        del event["home_team"], event["away_team"]
        market = event["bookmakers"][0]["markets"][0]
        market["key"] = "spreads"
        market["outcomes"] = [{"point": -0.25, "price": 1.91}]
        inputs[2] = json.dumps(envelope).encode()
        with self.assertRaisesRegex(ValueError, "distinct home and away"):
            self.capture(inputs)

    def test_no_asian_distribution_inferred_from_1x2_forecast(self):
        inputs = list(pipeline_inputs())
        forecasts = json.loads(inputs[1])
        forecasts[0].pop("score_probabilities")
        forecasts[0].update(p_home=0.3, p_draw=0.3, p_away=0.4)
        inputs[1] = json.dumps(forecasts).encode()
        with self.assertRaisesRegex(ValueError, "score probabilities"):
            self.capture(inputs)

    def test_metadata_cannot_relabel_bound_source_fields(self):
        for field, value in (("event_id", "wrong"), ("provider_event_id", "wrong"),
                             ("bookmaker", "wrong"), ("market", "handicap"),
                             ("model_version", "wrong"),
                             ("kickoff_utc", "2026-11-06T14:00:00Z")):
            inputs = list(pipeline_inputs())
            inputs[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.capture(inputs)

    def test_receipt_times_cannot_predate_sources_or_follow_kickoff(self):
        for field, value in (("odds_captured_utc", "2026-11-06T11:59:00Z"),
                             ("odds_captured_utc", "2026-11-06T13:00:00Z"),
                             ("odds_captured_utc", "2026-11-06T12:40:00Z"),
                             ("forecast_captured_utc", "2026-11-06T10:59:00Z"),
                             ("forecast_captured_utc", "2026-11-06T12:01:00Z")):
            inputs = list(pipeline_inputs())
            inputs[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.capture(inputs)

    def test_self_declared_source_event_bridge_is_not_verified_mapping(self):
        inputs = list(pipeline_inputs())
        forecasts = json.loads(inputs[1])
        forecasts[0]["event_id"] = inputs[0]["event_id"] = "internal-event"
        inputs[1] = json.dumps(forecasts).encode()
        with self.assertRaises(ValueError):
            self.capture(inputs)
        forecasts[0]["provider_event_id"] = "synthetic-1"
        inputs[1] = json.dumps(forecasts).encode()
        with self.assertRaises(ValueError):
            self.capture(inputs)

    def test_duplicate_quotes_rejected_by_existing_join(self):
        inputs = list(pipeline_inputs())
        envelope = json.loads(inputs[2])
        outcomes = envelope["data"][0]["bookmakers"][0]["markets"][0]["outcomes"]
        outcomes.append(dict(outcomes[0], point="2.50"))
        inputs[2] = json.dumps(envelope).encode()
        with self.assertRaisesRegex(ValueError, "duplicate quote"):
            self.capture(inputs)

    def test_cli_integrates_and_refuses_overwrite(self):
        inputs = pipeline_inputs()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            args = ["capture", "--bind-market-inputs"]
            for name, payload in zip(("metadata", "forecast", "odds", "model"),
                                     (json.dumps(inputs[0]).encode(), *inputs[1:])):
                target = root / name
                target.write_bytes(payload)
                args.extend(["--" + name, str(target)])
            output = root / "capture.json"
            args.extend(["--output", str(output)])
            with patch("sys.argv", args), patch("builtins.print"):
                capture_module.main()
            original = output.read_bytes()
            saved = json.loads(original)
            self.assertEqual(saved["record_sha256"], canonical_record_sha256(saved["record"]))
            self.assertEqual(Path(saved["record"]["source_files"]["odds"]).read_bytes(), inputs[2])
            with patch("sys.argv", args), self.assertRaises(FileExistsError):
                capture_module.main()
            self.assertEqual(output.read_bytes(), original)
            # Invalid source metadata must not produce even a partial capture.
            m = dict(inputs[0])
            del m["license_reference"]
            (root / "metadata").write_text(json.dumps(m))
            args[-1] = str(root / "rejected.json")
            with patch("sys.argv", args), self.assertRaises(ValueError):
                capture_module.main()
            self.assertFalse((root / "rejected.json").exists())


if __name__ == "__main__":
    unittest.main()
