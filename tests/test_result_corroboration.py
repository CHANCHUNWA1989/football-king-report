import unittest
from research_quality.result_corroboration import corroborate

def item(provider, score, event="fixture-1"):
    return {"provider": provider, "score_ft": score, "event_key": event, "status": "FINISHED"}

class ResultCorroborationTests(unittest.TestCase):
    def test_matching_publishers_are_not_automatically_independent(self):
        r = corroborate([item("feed-a", [2, 0]), item("feed-b", [2, 0])])
        self.assertEqual(r["fixture-1"]["status"], "CORROBORATED")
        self.assertFalse(r["fixture-1"]["independently_verified"])

    def test_conflicting_scores_held(self):
        r = corroborate([item("feed-a", [2, 0]), item("feed-b", [1, 0])])
        self.assertEqual(r["fixture-1"]["status"], "HOLD")

    def test_one_provider_held(self):
        self.assertEqual(corroborate([item("feed-a", [2, 0])])["fixture-1"]["status"], "HOLD")

    def test_same_provider_not_double_counted(self):
        r = corroborate([item("feed-a", [2, 0]), item("feed-a", [2, 0])])
        self.assertEqual(r["fixture-1"]["status"], "HOLD")

    def test_conflicting_same_provider_held(self):
        r = corroborate([item("feed-a", [2, 0]), item("feed-a", [3, 0]), item("feed-b", [2, 0])])
        self.assertEqual(r["fixture-1"]["status"], "HOLD")

    def test_invalid_score_rejected(self):
        with self.assertRaises(ValueError):
            corroborate([item("feed-a", [True, 0])])
