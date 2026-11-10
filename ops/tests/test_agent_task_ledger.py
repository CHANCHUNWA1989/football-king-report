import unittest
from ops.agent_task_ledger import plan


class AgentTaskLedgerTests(unittest.TestCase):
    def test_tasks_are_explicitly_not_executed(self):
        result = plan()
        self.assertEqual(len(result["tasks"]), 5)
        self.assertEqual(result["tasks"][0]["state"], "PENDING")
        self.assertEqual(result["tasks"][1]["state"], "BLOCKED")
        self.assertFalse(result["independent_agent_execution_confirmed"])
        self.assertEqual(result["production_recommendations"], "DISABLED")

    def test_forged_verification_cannot_unlock_downstream(self):
        result = plan({"provider_data": {
            "independent_review_verified": True,
            "source_authenticated": True,
            "evidence_ref": "github://fake/report"}})
        self.assertEqual(result["tasks"][0]["state"], "EVIDENCE_SUBMITTED")
        self.assertEqual(result["tasks"][1]["state"], "BLOCKED")
        self.assertEqual(result["verified_task_count"], 0)

    def test_invalid_evidence_fails_closed(self):
        result = plan({"provider_data": {"independent_review_verified": True,
                                          "evidence_ref": "https://example.com"}})
        self.assertEqual(result["tasks"][0]["state"], "PENDING")
        self.assertEqual(result["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
