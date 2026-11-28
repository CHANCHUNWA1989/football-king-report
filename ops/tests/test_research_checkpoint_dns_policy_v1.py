import unittest
from ops.research_checkpoint_dns_policy_v1 import inspect_checkpoint_dns_answers

class CheckpointDNSPolicyTests(unittest.TestCase):
    def test_public_address_passes_policy_but_not_provenance(self):
        result=inspect_checkpoint_dns_answers("https://example.org/checkpoint",["8.8.8.8"])
        self.assertTrue(result["dns_answer_policy_checked"])
        self.assertFalse(result["dns_resolution_verified"])
        self.assertFalse(result["connection_pinned_to_answers"])
        self.assertEqual(result["status"],"HOLD")
    def test_nonpublic_and_duplicate_answers_rejected(self):
        for addresses in ([],["127.0.0.1"],["10.0.0.1"],
                          ["192.168.1.1"],["169.254.169.254"],
                          ["::1"],["fc00::1"],["fe80::1"],
                          ["8.8.8.8","127.0.0.1"],
                          ["8.8.8.8","8.8.8.8"],["not-an-ip"]):
            with self.subTest(addresses=addresses):
                with self.assertRaises(ValueError):
                    inspect_checkpoint_dns_answers("https://example.org/x",addresses)

if __name__=="__main__":unittest.main()
