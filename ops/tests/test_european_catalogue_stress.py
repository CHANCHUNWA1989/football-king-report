"""Deterministic offline load and adversarial tests. No API credits or requests."""
import json
import time
import unittest

from ops.european_sports_catalogue import reconcile


class TestEuropeanCatalogueStress(unittest.TestCase):
    def test_ten_thousand_entries_and_repeated_calls(self):
        sports = [{"key": "unused_" + str(i), "active": True} for i in range(9992)]
        sports += [{"key": k, "active": True} for k in (
            "soccer_uefa_champs_league", "soccer_uefa_europa_league",
            "soccer_uefa_europa_conference_league", "soccer_epl",
            "soccer_spain_la_liga", "soccer_italy_serie_a",
            "soccer_germany_bundesliga", "soccer_france_ligue_one")]
        started = time.monotonic()
        for _ in range(100):
            result = reconcile(sports)
            self.assertEqual(result["status"], "HOLD")
            self.assertEqual(len(result["results"]), 8)
            self.assertTrue(all(x["catalogue_status"] == "ACTIVE_CANDIDATE"
                                for x in result["results"]))
            self.assertTrue(all(x["production_recommendations"] == "DISABLED"
                                for x in result["results"]))
        elapsed = time.monotonic() - started
        print("catalogue_stress_100x_10000_entries_seconds=%.3f" % elapsed)
        # CI timing is diagnostic only; never make a flaky timing assertion.

    def test_three_duplicates_fail_closed(self):
        sports = [{"key": "soccer_epl", "active": True}] * 3
        report = reconcile(sports)
        epl = next(x for x in report["results"] if x["competition"] == "premier-league")
        self.assertEqual(epl["catalogue_status"], "NOT_VERIFIED")

    def test_malformed_and_oversized_rejected(self):
        for value in (None, {}, "invalid", list(range(10001))):
            with self.subTest(kind=type(value).__name__):
                with self.assertRaises(ValueError):
                    reconcile(value)

    def test_mixed_invalid_entries_never_enable_betting(self):
        sports = [None, 12, [], {"key": None}, {"key": "soccer_epl", "active": "true"},
                  {"key": "soccer_epl", "active": True}]
        report = reconcile(sports)
        self.assertEqual(report["status"], "HOLD")
        self.assertEqual(report["production_recommendations"], "DISABLED")


if __name__ == "__main__":
    unittest.main()
