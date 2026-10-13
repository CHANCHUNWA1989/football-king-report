import unittest
from shadow_source_gap_matrix import matrix

class GapMatrixTests(unittest.TestCase):
    def test_missing_sources_remain_hold(self):
        c={"status":"HOLD","matured_unmatched_fixtures":[{"fixture_id":"one","home":"FC Bayern München","away":"FC Augsburg","kickoff_utc":"2026-10-10T13:30:00+00:00"}]}
        b={"status":"HOLD","independently_verified":False,"sources":[{"provider":"OpenLigaDB","records":[]},{"provider":"OpenFootball","records":[]}]}
        result=matrix(c,b)
        self.assertEqual(result["missing_source_fixture_count"],1)
        self.assertEqual(result["fixtures"][0]["reason"],"MISSING_SOURCE_RECORDS")
        self.assertFalse(result["eligible_for_model_scoring"])
    def test_forged_verification_rejected(self):
        with self.assertRaises(ValueError):matrix({"status":"HOLD"},{"status":"HOLD","independently_verified":True})
    def test_duplicate_source_rejected(self):
        with self.assertRaises(ValueError):matrix({"status":"HOLD"},{"status":"HOLD","independently_verified":False,"sources":[{"provider":"OpenLigaDB","records":[]},{"provider":"OpenLigaDB","records":[]}]})
if __name__=="__main__":unittest.main()
