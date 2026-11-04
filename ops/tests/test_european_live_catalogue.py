import unittest
from unittest.mock import patch

from ops.european_live_catalogue import verify_european_catalogue


class TestEuropeanLiveCatalogue(unittest.TestCase):
    def test_provider_catalogue_only_not_odds(self):
        fake = ([{"key": "soccer_epl", "active": True}], {"used": 0, "remaining": 500, "last": 0})
        with patch("ops.european_live_catalogue.retrieve", return_value=fake) as retrieve:
            result = verify_european_catalogue("test-secret", opener=lambda *a, **k: None)
        self.assertEqual(retrieve.call_args.args[:2], ("/sports/", "test-secret"))
        self.assertEqual(result["status"], "HOLD")
        self.assertTrue(result["connected"])
        self.assertTrue(result["catalogue_only"])
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(any(r["live_odds_verified"] for r in result["results"]))

    def test_bad_catalogue_rejected(self):
        with patch("ops.european_live_catalogue.retrieve", return_value=({}, {})):
            with self.assertRaises(ValueError):
                verify_european_catalogue("test-secret")


if __name__ == "__main__":
    unittest.main()
