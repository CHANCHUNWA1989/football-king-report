import unittest
from shared.execution_guard import authorize_execution, validate_proposal

P = {"proposal_id": "demo-1", "system": "football", "mode": "PAPER",
     "created_at": "2026-10-17T10:00:00+08:00",
     "expires_at": "2026-10-17T10:05:00+08:00",
     "instrument": "demo-market", "side": "home", "amount": 10.0}

class ExecutionGuardTests(unittest.TestCase):
    def test_paper_cannot_send_live(self):
        self.assertEqual(authorize_execution(P, approval={"approved": True})["reason"], "LIVE_EXECUTION_DISABLED")
    def test_live_mode_rejected(self):
        with self.assertRaises(ValueError):
            authorize_execution(dict(P, mode="LIVE"), approval={"approved": True})
    def test_research_mode_denied(self):
        self.assertFalse(authorize_execution(dict(P, mode="RESEARCH_ONLY"))["allowed"])
    def test_invalid_amount_rejected(self):
        with self.assertRaises(ValueError):
            validate_proposal(dict(P, amount=-1))
    def test_expiry_before_creation_rejected(self):
        with self.assertRaises(ValueError):
            validate_proposal(dict(P, expires_at="2026-10-17T09:00:00+08:00"))

if __name__ == "__main__":
    unittest.main()
