import hashlib
import unittest
from ops.research_forecast_artifact_integrity_v1 import inspect_forecast_artifact
from test_research_external_evidence_gate_v1 import candidate

class ForecastArtifactIntegrityTests(unittest.TestCase):
    def setup_candidate(self,artifact=b'forecast fixture test bytes'):
        item=candidate()
        digest=hashlib.sha256(artifact).hexdigest()
        item["forecast_sha256"]=digest
        item["forecast_archive"]["sha256"]=digest
        item["forecast_archive"]["receipt_sha256"]=digest
        return item,artifact
    def test_actual_bytes_match_but_timestamp_unverified(self):
        item,artifact=self.setup_candidate()
        result=inspect_forecast_artifact(item,artifact)
        self.assertTrue(result["artifact_integrity_verified"])
        self.assertFalse(result["third_party_receipt_verified"])
        self.assertFalse(result["immutable_timestamp_authenticated"])
        self.assertEqual(result["authenticated_samples"],0)
        self.assertEqual(result["status"],"HOLD")
    def test_tampered_artifact_rejected(self):
        item,artifact=self.setup_candidate()
        with self.assertRaises(ValueError):inspect_forecast_artifact(item,artifact+b'x')
    def test_empty_artifact_rejected(self):
        item,_=self.setup_candidate()
        with self.assertRaises(ValueError):inspect_forecast_artifact(item,b'')
    def test_oversized_artifact_rejected(self):
        item,_=self.setup_candidate()
        with self.assertRaises(ValueError):inspect_forecast_artifact(item,b'x'*5_000_001)
    def test_nonbytes_artifact_rejected(self):
        item,_=self.setup_candidate()
        with self.assertRaises(ValueError):inspect_forecast_artifact(item,"forecast")

if __name__=="__main__":unittest.main()
