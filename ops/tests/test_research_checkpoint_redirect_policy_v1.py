import unittest
from ops.research_checkpoint_redirect_policy_v1 import inspect_checkpoint_redirect_policy

class RedirectPolicyTests(unittest.TestCase):
    def test_200_without_redirect_metadata_passes_policy_only(self):
        result=inspect_checkpoint_redirect_policy("https://example.org/proof",200)
        self.assertTrue(result["redirect_policy_checked"])
        self.assertFalse(result["network_request_performed"])
        self.assertEqual(result["status"],"HOLD")
    def test_redirects_rejected(self):
        for status in (301,302,303,307,308):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    inspect_checkpoint_redirect_policy(
                        "https://example.org/proof",status,"http://127.0.0.1/")
    def test_unexpected_location_on_success_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_redirect_policy("https://example.org/proof",200,"https://other.example.org")
    def test_error_status_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_redirect_policy("https://example.org/proof",503)

if __name__=="__main__":unittest.main()
