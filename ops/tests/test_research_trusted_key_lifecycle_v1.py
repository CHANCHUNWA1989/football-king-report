import hashlib
import json
import unittest
from ops.research_trusted_key_lifecycle_v1 import inspect_key_lifecycle

class KeyLifecycleTests(unittest.TestCase):
    def fixture(self):
        binding={"issuer":"test issuer","key_id":"k2","public_key_sha256":"a"*64}
        registry={"schema":"football-king-trusted-key-registry-v1",
                  "keys":[{"issuer":"test issuer","key_id":"k1","public_key_sha256":"b"*64,
                           "not_before":"2025-01-01T00:00:00Z","not_after":"2026-01-01T00:00:00Z","state":"revoked"},
                          {"issuer":"test issuer","key_id":"k2","public_key_sha256":"a"*64,
                           "not_before":"2026-01-01T00:00:00Z","not_after":"2027-01-01T00:00:00Z","state":"active"}]}
        return binding,registry
    def pin(self,registry):
        return hashlib.sha256(json.dumps(registry,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    def verify(self,binding,registry,when="2026-11-28T00:00:00Z"):
        return inspect_key_lifecycle(binding,registry,self.pin(registry),when)
    def test_active_key_still_hold(self):
        binding,registry=self.fixture()
        result=self.verify(binding,registry)
        self.assertTrue(result["key_lifecycle_checked"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertEqual(result["status"],"HOLD")
    def test_revoked_old_key_rejected(self):
        binding,registry=self.fixture()
        binding.update(key_id="k1",public_key_sha256="b"*64)
        with self.assertRaises(ValueError):
            self.verify(binding,registry)
    def test_expired_key_rejected(self):
        binding,registry=self.fixture()
        with self.assertRaises(ValueError):
            self.verify(binding,registry,"2027-01-01T00:00:00Z")
    def test_not_yet_valid_key_rejected(self):
        binding,registry=self.fixture()
        with self.assertRaises(ValueError):
            self.verify(binding,registry,"2025-12-31T23:59:59Z")
    def test_tampered_registry_pin_rejected(self):
        binding,registry=self.fixture()
        with self.assertRaises(ValueError):
            inspect_key_lifecycle(binding,registry,"0"*64,"2026-11-28T00:00:00Z")
    def test_duplicate_key_identity_rejected(self):
        binding,registry=self.fixture()
        registry["keys"].append(dict(registry["keys"][1]))
        with self.assertRaises(ValueError):
            self.verify(binding,registry)
    def test_naive_verification_time_rejected(self):
        binding,registry=self.fixture()
        with self.assertRaises(ValueError):
            self.verify(binding,registry,"2026-11-28T00:00:00")

if __name__=="__main__":unittest.main()
