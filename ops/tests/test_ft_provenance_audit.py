import unittest
from ft_provenance_audit import provenance_status

class ProvenanceTests(unittest.TestCase):
    def test_missing_metadata(self):
        self.assertEqual(provenance_status({}),"MISSING_PROVENANCE")

    def test_valid_metadata_does_not_claim_verification(self):
        item={"source_urls":["https://example.org/match","https://other.org/match"],
              "raw_sha256":["a"*64,"b"*64]}
        self.assertEqual(provenance_status(item),"METADATA_PRESENT_UNVERIFIED")

    def test_same_host_is_not_independent(self):
        item={"source_urls":["https://example.org/one","https://example.org/two"],
              "raw_sha256":["a"*64,"b"*64]}
        self.assertEqual(provenance_status(item),"NON_INDEPENDENT_HOSTS")

    def test_bad_digest_rejected(self):
        item={"source_urls":["https://example.org/one","https://other.org/two"],
              "raw_sha256":["bad","b"*64]}
        self.assertEqual(provenance_status(item),"INVALID_PROVENANCE")

if __name__=="__main__":
    unittest.main()
