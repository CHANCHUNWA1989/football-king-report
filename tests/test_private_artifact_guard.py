import json
import unittest
from ops.private_artifact_guard import sanitize

class ArtifactSafety(unittest.TestCase):
    def test_no_raw_licensed_quotes_or_identity_can_escape(self):
        raw = {
            "input_status": "CONNECTED",
            "counts": {"RESEARCH_ONLY": 2, "VERIFIED_VALUE": 500},
            "coverage": [{"league": "epl", "quotes": 2,
                          "bookmaker": "secretbook", "decimal_odds": 2.35,
                          "home": "Secret Home", "away": "Secret Away"}],
            "requested_markets": ["h2h", "invalid", "spreads"],
            "candidates": [{"fixture_id": "private-fixture",
                            "source": "secretbook", "decimal_odds": 2.35,
                            "selection": "Secret Home"}]}
        ready = {"grounded_progress": {"settled_cases_in_archive": 1,
                                       "additional_settled_cases_needed": 299,
                                       "secret_raw_odds": "do not upload"}}
        output = sanitize(raw, ready)
        serialized = json.dumps(output)
        for secret in ("secretbook", "private-fixture", "Secret Home",
                       "Secret Away", "2.35", "decimal_odds", "secret_raw_odds"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(output["counts"]["VERIFIED_VALUE"], 0)
        self.assertEqual(output["requested_markets"], ["h2h", "spreads"])
        self.assertEqual(output["production_recommendations"], "DISABLED")

if __name__ == "__main__":
    unittest.main()
