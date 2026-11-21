"""Offline tests. Values are SYNTHETIC, not actual HKJC market prices."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hkjc_market_reference_gate import audit, _reference_decimal

NOW = "2026-11-21T08:05:00Z"  # 16:05 HKT


def row():
    return {
        "source_type": "THIRD_PARTY_HKJC_MIRROR",
        "source_url": "https://bogo.hk/hkjc-football",
        "source_fixture_id": "example-fixture-1",
        "home": "Synthetic Home", "away": "Synthetic Away",
        "kickoff_utc": "2026-11-21T11:00:00Z",
        "source_updated_utc": "2026-11-21T08:04:00Z",
        "captured_utc": "2026-11-21T08:04:30Z",
        "market": "TOTALS", "selection": "UNDER", "line": 2.5,
        "price_format": "HK_ODDS_WATER", "price": 0.91,
    }


class ReferenceGateTests(unittest.TestCase):
    def check_restricted(self, result):
        self.assertEqual(result["production_recommendations"], "DISABLED")
        for key in ("official_hkjc_quote_authenticated",
                    "licensed_executable_quote_verified", "positive_ev_verified",
                    "betting_authorized", "eligible_for_formal_forward_scoring",
                    "formal_prematch_prediction_sealed",
                    "source_original_update_authenticated"):
            self.assertFalse(result[key])
        self.assertNotIn("price", result)
        self.assertNotIn("normalized_decimal_reference_price", result)

    def test_fresh_mirror_is_only_research_not_hkjc_authenticated(self):
        result = audit(row(), as_of_utc=NOW)
        self.check_restricted(result)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["reason"], "THIRD_PARTY_MIRROR_NOT_HKJC_AUTHENTICATED")
        self.assertTrue(result["reference_price_at_least_1_80"])
        self.assertEqual(result["line_quarters"], 10)

    def test_hk_water_plus_one_decimal_only_in_private_math(self):
        self.assertAlmostEqual(_reference_decimal(0.91, "HK_ODDS_WATER"), 1.91)
        self.assertAlmostEqual(_reference_decimal(1.08, "HK_ODDS_WATER"), 2.08)

    def test_stale_mirror_with_1357_publication_time_is_hold(self):
        case = row()
        case["source_updated_utc"] = "2026-11-21T05:57:00Z"
        result = audit(case, as_of_utc=NOW)
        self.check_restricted(result)
        self.assertEqual(result["status"], "HOLD")
        self.assertEqual(result["reason"], "STALE_OR_FUTURE_SOURCE_TIME")
        self.assertFalse(result["reference_price_at_least_1_80"])

    def test_missing_upstream_original_time_is_hold(self):
        case = row(); case["source_updated_utc"] = None
        result = audit(case, as_of_utc=NOW)
        self.check_restricted(result)
        self.assertEqual(result["status"], "HOLD")

    def test_fake_official_label_on_mirror_domain_is_hold(self):
        case = row(); case["source_type"] = "HKJC_MANUAL_REFERENCE"
        result = audit(case, as_of_utc=NOW)
        self.check_restricted(result)
        self.assertEqual(result["reason"], "UNTRUSTED_OR_MISMATCHED_SOURCE_URL")

    def test_official_url_manual_reference_is_still_not_a_live_offer(self):
        case = row()
        case["source_type"] = "HKJC_MANUAL_REFERENCE"
        case["source_url"] = "https://football.hkjc.com/zh-hk/home"
        result = audit(case, as_of_utc=NOW)
        self.check_restricted(result)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["reason"], "MANUAL_REFERENCE_NOT_HKJC_AUTHENTICATED")

    def test_spoofed_official_domain_rejected(self):
        case = row(); case["source_url"] = "https://bogo.hk.attacker.example/hkjc"
        self.assertEqual(audit(case, as_of_utc=NOW)["status"], "HOLD")

    def test_quarter_handicap_line_is_not_rounded_to_half(self):
        case = row(); case["market"] = "ASIAN_HANDICAP"
        case["selection"] = "HOME";case["line"] = -0.75
        result = audit(case, as_of_utc=NOW)
        self.assertEqual(result["line_quarters"], -3)
        self.check_restricted(result)

    def test_non_quarter_point_rejected(self):
        case = row();case["line"] = 2.6
        result = audit(case, as_of_utc=NOW)
        self.assertEqual(result["reason"], "INVALID_ASIAN_QUARTER_POINT")

    def test_1x2_decimal_supported_but_not_hk_water(self):
        case = row();case["market"] = "FT_1X2"; case["selection"] = "AWAY"
        case["line"] = None;case["price_format"] = "DECIMAL";case["price"] = 2.54
        result = audit(case, as_of_utc=NOW)
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.check_restricted(result)
        case["price_format"] = "HK_ODDS_WATER"
        self.assertEqual(audit(case, as_of_utc=NOW)["status"], "HOLD")

    def test_boolean_price_and_line_rejected(self):
        case = row();case["price"] = True
        self.assertEqual(audit(case, as_of_utc=NOW)["status"], "HOLD")
        case = row();case["line"] = False
        self.assertEqual(audit(case, as_of_utc=NOW)["status"], "HOLD")

    def test_future_source_timestamp_rejected(self):
        case = row();case["source_updated_utc"] = "2026-11-21T08:07:00Z"
        self.assertEqual(audit(case, as_of_utc=NOW)["reason"], "STALE_OR_FUTURE_SOURCE_TIME")

    def test_near_kickoff_is_not_a_new_prematch_forecast(self):
        case = row();case["kickoff_utc"] = "2026-11-21T08:07:00Z"
        self.assertEqual(audit(case, as_of_utc=NOW)["reason"], "IN_PLAY_OR_TOO_CLOSE_TO_KICKOFF")

    def test_naive_timestamp_rejected(self):
        case = row();case["captured_utc"] = "2026-11-21T08:04:30"
        self.assertEqual(audit(case, as_of_utc=NOW)["reason"], "NAIVE_TIMESTAMP")

    def test_extra_fields_rejected_no_claimed_ev(self):
        case = row();case["verified_ev"] = 0.1
        self.assertEqual(audit(case, as_of_utc=NOW)["reason"], "MISSING_OR_EXTRA_FIELDS")

    def test_cli_writes_redacted_report_and_preserves_source(self):
        import json
        import tempfile
        from hkjc_market_reference_gate import main
        with tempfile.TemporaryDirectory() as directory:
            inp = Path(directory) / "snapshot.json"
            out = Path(directory) / "report.json"
            original = json.dumps(row())
            inp.write_text(original, encoding="utf-8")
            main(["--input", str(inp), "--as-of-utc", NOW,
                  "--output", str(out)])
            self.assertEqual(inp.read_text(encoding="utf-8"), original)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "RESEARCH_ONLY")
            self.check_restricted(result)
            self.assertNotIn('"price"', out.read_text(encoding="utf-8"))

    def test_cli_refuses_source_overwrite(self):
        import json
        import tempfile
        from hkjc_market_reference_gate import main
        with tempfile.TemporaryDirectory() as directory:
            inp = Path(directory) / "snapshot.json"
            inp.write_text(json.dumps(row()), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["--input", str(inp), "--as-of-utc", NOW,
                      "--output", str(inp)])

    def test_no_score_or_realized_profit_output(self):
        result = audit(row(), as_of_utc=NOW)
        for key in ("score_ft", "profit", "roi", "ev", "forecast_probability"):
            self.assertNotIn(key, result)
        self.check_restricted(result)


if __name__ == "__main__":
    unittest.main()
