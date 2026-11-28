import unittest
from ops.research_checkpoint_tls_metadata_v1 import inspect_checkpoint_tls_metadata

class TLSMetadataTests(unittest.TestCase):
    def test_consistent_metadata_is_not_tls_proof(self):
        result=inspect_checkpoint_tls_metadata(
            "https://example.org/proof","example.org","example.org",True)
        self.assertTrue(result["tls_metadata_consistent"])
        self.assertFalse(result["tls_peer_authenticated"])
        self.assertFalse(result["tls_handshake_performed"])
        self.assertEqual(result["status"],"HOLD")
    def test_mismatched_sni_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_tls_metadata(
                "https://example.org/proof","other.org","example.org",True)
    def test_mismatched_certificate_hostname_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_tls_metadata(
                "https://example.org/proof","example.org","other.org",True)
    def test_unverified_certificate_claim_rejected(self):
        with self.assertRaises(ValueError):
            inspect_checkpoint_tls_metadata(
                "https://example.org/proof","example.org","example.org",False)

if __name__=="__main__":unittest.main()
