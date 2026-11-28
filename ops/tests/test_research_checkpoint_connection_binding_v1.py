import unittest
from ops.research_checkpoint_connection_binding_v1 import inspect_checkpoint_connection_binding

class ConnectionBindingTests(unittest.TestCase):
    def test_approved_target_is_not_network_proof(self):
        result=inspect_checkpoint_connection_binding(
            "https://example.org/checkpoint",["8.8.8.8","1.1.1.1"],"1.1.1.1")
        self.assertTrue(result["connection_target_matches_approved_answers"])
        self.assertFalse(result["connection_pinned_to_answers"])
        self.assertFalse(result["socket_connection_performed"])
        self.assertEqual(result["status"],"HOLD")
    def test_mismatched_target_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_connection_binding(
                "https://example.org/checkpoint",["8.8.8.8"],"1.1.1.1")
    def test_private_target_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_connection_binding(
                "https://example.org/checkpoint",["8.8.8.8"],"127.0.0.1")
    def test_private_dns_set_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_connection_binding(
                "https://example.org/checkpoint",["10.0.0.1"],"10.0.0.1")

if __name__=="__main__":unittest.main()
