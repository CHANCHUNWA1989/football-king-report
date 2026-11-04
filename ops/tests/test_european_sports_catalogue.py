import unittest
from ops.european_sports_catalogue import reconcile


class TestEuropeanSportsCatalogue(unittest.TestCase):
    def test_active_is_not_live_odds_entitlement(self):
        report = reconcile([{"key": "soccer_epl", "active": True}])
        self.assertEqual(report["status"], "HOLD")
        epl = next(r for r in report["results"] if r["competition"] == "premier-league")
        self.assertEqual(epl["catalogue_status"], "ACTIVE_CANDIDATE")
        self.assertFalse(epl["season_entitled"])
        self.assertFalse(epl["live_odds_verified"])

    def test_duplicate_provider_key_fails_closed(self):
        report = reconcile([
            {"key": "soccer_epl", "active": True},
            {"key": "soccer_epl", "active": True},
        ])
        epl = next(r for r in report["results"] if r["competition"] == "premier-league")
        self.assertEqual(epl["catalogue_status"], "NOT_VERIFIED")

    def test_rejects_invalid_catalogue(self):
        with self.assertRaises(ValueError):
            reconcile({"sports": []})


if __name__ == "__main__":
    unittest.main()
