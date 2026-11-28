import hashlib
import json
import unittest
from ops.research_key_revocation_history_v1 import inspect_revocation_history

class RevocationHistoryTests(unittest.TestCase):
    def fixture(self):
        binding={"issuer":"test issuer","key_id":"k2"}
        history={"schema":"football-king-key-revocation-history-v1",
                 "events":[{"issuer":"test issuer","key_id":"k1",
                            "revoked_at":"2026-03-01T00:00:00Z","reason":"retired"},
                           {"issuer":"test issuer","key_id":"k2",
                            "revoked_at":"2026-12-01T00:00:00Z","reason":"rotation"}]}
        pin=hashlib.sha256(json.dumps(history,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        return binding,history,pin
    def test_future_revocation_does_not_claim_authentication(self):
        binding,history,pin=self.fixture()
        result=inspect_revocation_history(binding,history,pin,"2026-11-28T00:00:00Z")
        self.assertTrue(result["not_revoked_at_verification_time"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertEqual(result["status"],"HOLD")
    def test_revocation_effective_inclusive(self):
        binding,history,pin=self.fixture()
        with self.assertRaises(ValueError):
            inspect_revocation_history(binding,history,pin,"2026-12-01T00:00:00Z")
    def test_bad_pin_rejected(self):
        binding,history,_=self.fixture()
        with self.assertRaises(ValueError):
            inspect_revocation_history(binding,history,"0"*64,"2026-11-28T00:00:00Z")
    def test_duplicate_revocation_rejected(self):
        binding,history,_=self.fixture()
        history["events"].append(dict(history["events"][0]))
        pin=hashlib.sha256(json.dumps(history,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
        with self.assertRaises(ValueError):
            inspect_revocation_history(binding,history,pin,"2026-11-28T00:00:00Z")
    def test_missing_timezone_rejected(self):
        binding,history,pin=self.fixture()
        with self.assertRaises(ValueError):
            inspect_revocation_history(binding,history,pin,"2026-11-28T00:00:00")

if __name__=="__main__":unittest.main()
