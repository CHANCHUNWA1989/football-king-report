import unittest
from ops.research_checkpoint_locator_policy_v1 import inspect_checkpoint_locator

class CheckpointLocatorPolicyTests(unittest.TestCase):
    def test_public_https_name_passes_policy_only(self):
        result=inspect_checkpoint_locator("https://example.org/proof")
        self.assertTrue(result["locator_policy_checked"])
        self.assertFalse(result["network_retrieval_performed"])
        self.assertEqual(result["status"],"HOLD")
    def test_unsafe_locators_rejected(self):
        for locator in ("http://example.org/x","https://localhost/x",
                        "https://127.0.0.1/x","https://[::1]/x",
                        "https://user:pass@example.org/x",
                        "https://example.org:8080/x","https://example.org/x#fragment",
                        "https://internal.local/x","https://example.org/x\n"):
            with self.subTest(locator=locator):
                with self.assertRaises(ValueError):
                    inspect_checkpoint_locator(locator)

if __name__=="__main__":unittest.main()
