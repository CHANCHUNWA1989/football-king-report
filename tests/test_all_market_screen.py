import unittest
from datetime import datetime, timezone, timedelta
from ops.all_market_screen import screen

NOW = datetime(2026, 10, 10, 10, tzinfo=timezone.utc)
def quote(**kwargs):
    q = {"fixture_id": "fixture-1", "market": "asian_handicap", "selection": "home",
         "line": -1.25, "decimal_odds": 2.1, "source": "example",
         "observed_utc": (NOW-timedelta(minutes=2)).isoformat(),
         "kickoff_utc": (NOW+timedelta(hours=2)).isoformat()}
    q.update(kwargs)
    return q

class TestAllMarketScreen(unittest.TestCase):
    def test_unrepresentable_utc_quote_timestamps_fail_closed(self):
        for field in ("observed_utc", "kickoff_utc"):
            for timestamp in ("0001-01-01T00:00:00+14:00",
                              "9999-12-31T23:59:59-14:00"):
                with self.subTest(field=field, timestamp=timestamp):
                    q = quote(**{field: timestamp}, settlement_probabilities={
                        "full_win": .4, "half_win": .2, "push": 0,
                        "half_loss": .1, "full_loss": .3})
                    try:
                        report = screen({"quotes": [q]}, NOW)
                    except OverflowError:
                        self.fail("Untrusted quote timestamp escaped the INVALID guard")
                    row = report["candidates"][0]
                    self.assertEqual(row["status"], "INVALID")
                    self.assertEqual(row["reason"], "PRICE_OR_TIME_INVALID")
                    self.assertNotIn("ev_per_unit", row)
                    self.assertEqual(report["counts"]["VERIFIED_VALUE"], 0)

    def test_equivalent_timezones_preserve_quote_chronology_and_research_ev(self):
        q = quote(observed_utc="2026-10-10T17:58:00+08:00",
                  captured_utc="2026-10-10T17:59:00+08:00",
                  kickoff_utc="2026-10-10T20:00:00+08:00",
                  settlement_probabilities={"full_win": .4, "half_win": .2,
                                            "push": 0, "half_loss": .1, "full_loss": .3})
        report = screen({"quotes": [q]}, NOW)
        row = report["candidates"][0]
        self.assertEqual(row["status"], "RESEARCH_ONLY")
        self.assertEqual(row["quote_age_seconds"], 120)
        self.assertAlmostEqual(row["ev_per_unit"], .2)
        for field in ("observed_utc", "captured_utc", "kickoff_utc"):
            self.assertEqual(row[field], q[field])
        self.assertEqual(report["quote_evidence_validation"]["production_recommendations"],
                         "DISABLED")

    def test_capture_time_is_preserved_separately_from_source_update(self):
        captured = (NOW-timedelta(minutes=1)).isoformat()
        item = screen({"quotes": [quote(captured_utc=captured)]}, NOW)["candidates"][0]
        self.assertEqual(item["captured_utc"], captured)
        self.assertEqual(item["observed_utc"], (NOW-timedelta(minutes=2)).isoformat())
        self.assertEqual(item["status"], "RESEARCH_ONLY")

    def test_missing_probability_is_research_only(self):
        self.assertEqual(screen({"quotes": [quote()]}, NOW)["candidates"][0]["status"], "RESEARCH_ONLY")
    def test_half_settlement_ev(self):
        q = quote(settlement_probabilities={"full_win": .4, "half_win": .2, "push": 0,
                                            "half_loss": .1, "full_loss": .3},
                  independently_calibrated=True, lineup_checked=True, source_verified=True)
        item = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertAlmostEqual(item["ev_per_unit"], .2)
        self.assertEqual(item["status"], "RESEARCH_ONLY")
        self.assertEqual(item["reason"], "INDEPENDENT_CERTIFICATION_GATE_NOT_IMPLEMENTED")
    def test_self_attested_flags_never_certify(self):
        p = {"full_win": 0.51, "half_win": 0, "push": 0, "half_loss": 0, "full_loss": 0.49}
        q = quote(settlement_probabilities=p, independently_calibrated=True,
                  lineup_checked=True, source_verified=True,
                  external_validation_record_verified=True)
        result = screen({"quotes": [q]}, NOW)
        self.assertEqual(result["candidates"][0]["status"], "RESEARCH_ONLY")
        self.assertEqual(result["counts"]["VERIFIED_VALUE"], 0)

    def test_malformed_payload_is_safe(self):
        self.assertEqual(screen({"quotes": None}, NOW)["candidates"], [])
        self.assertEqual(screen(None, NOW)["candidates"], [])
        self.assertEqual(screen({"quotes": [quote(observed_utc=123)]}, NOW)["candidates"][0]["status"], "INVALID")

    def test_stale_quote(self):
        item = screen({"quotes": [quote(observed_utc=(NOW-timedelta(hours=1)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "STALE")
    def test_reject_postkickoff(self):
        item = screen({"quotes": [quote(kickoff_utc=(NOW-timedelta(minutes=1)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "INVALID")
    def test_all_market_types_not_filtered(self):
        q = [quote(market=m, selection=s) for m,s in [("asian_handicap","away"),("totals","over"),("totals","under"),("h2h","home"),("btts","yes")]]
        self.assertEqual(len(screen({"quotes":q}, NOW)["candidates"]), 5)


    def test_capture_before_source_update_fails_closed(self):
        item = screen({"quotes": [quote(captured_utc=(NOW-timedelta(minutes=4)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "INVALID")
        self.assertEqual(item["reason"], "CAPTURE_BEFORE_SOURCE_UPDATE")

    def test_future_capture_fails_closed(self):
        item = screen({"quotes": [quote(captured_utc=(NOW+timedelta(seconds=30)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "INVALID")
        self.assertEqual(item["reason"], "FUTURE_CAPTURE")

    def test_postkickoff_capture_fails_closed(self):
        item = screen({"quotes": [quote(captured_utc=(NOW+timedelta(hours=3)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "INVALID")
        self.assertEqual(item["reason"], "POSTKICKOFF_CAPTURE")

    def test_malformed_capture_time_fails_closed(self):
        for capture in ("2026-10-10T09:59:00", "not-a-date", 123, None):
            with self.subTest(capture=capture):
                item = screen({"quotes": [quote(captured_utc=capture)]}, NOW)["candidates"][0]
                self.assertEqual(item["status"], "INVALID")
                self.assertEqual(item["reason"], "INVALID_CAPTURE_TIMESTAMP")

    def test_future_source_update_fails_closed_without_grace_period(self):
        item = screen({"quotes": [quote(observed_utc=(NOW+timedelta(seconds=30)).isoformat())]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "INVALID")
        self.assertEqual(item["reason"], "NON_PREMATCH_OR_FUTURE_QUOTE")

    def test_valid_capture_keeps_research_only_ev(self):
        q = quote(captured_utc=(NOW-timedelta(minutes=1)).isoformat(),
                  settlement_probabilities={"full_win": .4, "half_win": .2,
                                            "push": 0, "half_loss": .1, "full_loss": .3})
        item = screen({"quotes": [q]}, NOW)["candidates"][0]
        self.assertEqual(item["status"], "RESEARCH_ONLY")
        self.assertAlmostEqual(item["ev_per_unit"], .2)
        self.assertEqual(item["reason"], "INDEPENDENT_CERTIFICATION_GATE_NOT_IMPLEMENTED")

if __name__ == "__main__":
    unittest.main()
