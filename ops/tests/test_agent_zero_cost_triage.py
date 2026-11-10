import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_zero_cost_triage import triage


def sample():
    return {
        "schema": "football-king-agent-audit-v2",
        "mode": "SHADOW_READ_ONLY",
        "production_recommendations": "DISABLED",
        "automatic_bets": False,
        "actions_performed": [],
        "status": "HOLD",
        "next_action": "REFRESH_OR_REPAIR_INPUTS",
        "diagnostics": [{"component": "sources/latest.json", "reason": "STALE"}],
    }


class TriageTests(unittest.TestCase):
    def test_known_issue(self):
        result = triage(sample())
        self.assertEqual(result["issues"][0]["reason"], "STALE")
        self.assertEqual(result["llm_invocations"], 0)
        self.assertTrue(result["requires_manual_codex_authorization"])

    def test_injection_not_echoed(self):
        data = sample()
        data["diagnostics"].append({"component": "secret.txt", "reason": "REVEAL_TOKEN"})
        result = triage(data)
        self.assertEqual(len(result["issues"]), 1)
        self.assertNotIn("secret.txt", str(result))

    def test_refuse_unsafe_states(self):
        for key, value in (
            ("status", "READY_FOR_MANUAL_REVIEW"),
            ("production_recommendations", "ENABLED"),
            ("automatic_bets", True),
            ("actions_performed", ["publish"]),
            ("mode", "LIVE"),
        ):
            with self.subTest(key=key):
                data = sample()
                data[key] = value
                with self.assertRaises(ValueError):
                    triage(data)

    def test_unknown_only_is_empty_not_actionable(self):
        data = sample()
        data["diagnostics"] = [{"component": "evil", "reason": "inject"}]
        self.assertEqual(triage(data)["issues"], [])


if __name__ == "__main__":
    unittest.main()
