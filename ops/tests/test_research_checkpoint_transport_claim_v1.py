import unittest
from ops.research_checkpoint_transport_claim_v1 import inspect_checkpoint_transport_claim

class TransportClaimTests(unittest.TestCase):
    def fixture(self):
        return ["https://example.org/proof",["8.8.8.8"],"8.8.8.8",
                "example.org","example.org",True,200,None]
    def test_complete_metadata_remains_hold(self):
        result=inspect_checkpoint_transport_claim(*self.fixture())
        self.assertTrue(result["transport_metadata_policy_checked"])
        self.assertFalse(result["network_request_performed"])
        self.assertFalse(result["tls_peer_authenticated"])
        self.assertEqual(result["status"],"HOLD")
    def test_private_dns_rejected(self):
        args=self.fixture();args[1]=["127.0.0.1"]
        with self.assertRaises(ValueError):inspect_checkpoint_transport_claim(*args)
    def test_connection_ip_mismatch_rejected(self):
        args=self.fixture();args[2]="1.1.1.1"
        with self.assertRaises(ValueError):inspect_checkpoint_transport_claim(*args)
    def test_tls_name_mismatch_rejected(self):
        args=self.fixture();args[4]="other.org"
        with self.assertRaises(ValueError):inspect_checkpoint_transport_claim(*args)
    def test_redirect_rejected(self):
        args=self.fixture();args[6]=302;args[7]="https://other.org"
        with self.assertRaises(ValueError):inspect_checkpoint_transport_claim(*args)

if __name__=="__main__":unittest.main()
