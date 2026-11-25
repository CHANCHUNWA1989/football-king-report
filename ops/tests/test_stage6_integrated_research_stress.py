"""Cross-module synthetic integration checks; no live feeds or price claims."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_live_event_consensus import FIXTURE, DECISION, check, ev, feeds, overturn
from test_inplay_state_challenger_vnext import sample
from inplay_state_challenger_vnext import audit_predict, remaining_matrix
from score_distribution_vnext import market_distribution, one_x_two, GRADE_NAMES


def snapshot(proof, *, minute=45):
    s = sample(score=(proof.get("score_home", 1), proof.get("score_away", 0)),
               minute=minute, decision=DECISION)
    s["fixture_id"] = FIXTURE["fixture_id"]
    s["prematch"]["fixture_id"] = FIXTURE["fixture_id"]
    s["event_consensus"] = proof
    cards = proof.get("active_red_cards", {})
    s["red_home"], s["red_away"] = cards.get("HOME", 0), cards.get("AWAY", 0)
    return s


class IntegratedResearchStress(unittest.TestCase):
    def test_real_consensus_output_feeds_dynamic_and_market_matrix(self):
        baseline = audit_predict(snapshot(check()))
        card = ev(key="r1", kind="RED_CARD", side="AWAY", minute=34)
        result = audit_predict(snapshot(check(feeds(events=[ev(), card]))))
        self.assertEqual(baseline["status"], "RESEARCH_ONLY")
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertGreater(result["fulltime_probabilities"]["HOME"],
                           baseline["fulltime_probabilities"]["HOME"])
        g = remaining_matrix(result["remaining_expected_home_goals"],
                             result["remaining_expected_away_goals"], 1, 0)
        self.assertEqual(one_x_two(g), result["fulltime_probabilities"])
        reverse = dict(zip(GRADE_NAMES, reversed(GRADE_NAMES)))
        for quarter in range(-20, 21):
            line = quarter / 4
            h = market_distribution(g, market="asian_handicap", side="HOME", line=line)
            a = market_distribution(g, market="asian_handicap", side="AWAY", line=-line)
            for grade in GRADE_NAMES:
                self.assertAlmostEqual(h["outcome_probabilities"][grade],
                                       a["outcome_probabilities"][reverse[grade]], places=12)
        for quarter in range(81):
            line = quarter / 4
            o = market_distribution(g, market="totals", side="OVER", line=line)
            u = market_distribution(g, market="totals", side="UNDER", line=line)
            for grade in GRADE_NAMES:
                self.assertAlmostEqual(o["outcome_probabilities"][grade],
                                       u["outcome_probabilities"][reverse[grade]], places=12)
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["model_scoring_eligible"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_unmatched_card_blocks_downstream_prediction(self):
        rows = feeds()
        rows[0]["event_revisions"].append(ev(key="r1", kind="RED_CARD", side="AWAY", minute=34))
        result = audit_predict(snapshot(check(rows)))
        self.assertEqual(result["status"], "HOLD")
        self.assertNotIn("fulltime_probabilities", result)

    def test_pending_var_blocks_downstream_prediction(self):
        result = audit_predict(snapshot(check(feeds(events=overturn()[:2]))))
        self.assertEqual(result["status"], "HOLD")

    def test_late_observation_blocks_downstream_prediction(self):
        rows = feeds()
        rows[0]["event_revisions"][0]["received_utc"] = "2026-11-03T20:52:00Z"
        result = audit_predict(snapshot(check(rows)))
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
