import unittest
from shadow_ft_linkage_diagnostics import diagnose

class LinkageDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.sealed=[{"fixture_id":"f1","league":"bundesliga","home":"FC Bayern München","away":"FC Augsburg","kickoff_utc":"2026-10-10T13:30:00Z"}]
        self.bundle={"status":"HOLD","independently_verified":False,"sources":[]}
    def test_two_source_agreement_is_diagnostic_only(self):
        self.bundle["sources"]=[
            {"provider":"OpenLigaDB","records":[{"home":"FC Bayern München","away":"FC Augsburg","kickoff_utc":"2026-10-10T13:30:00Z","score_ft":[2,1],"status":"FINISHED"}]},
            {"provider":"OpenFootball","records":[{"home":"FC Bayern München","away":"FC Augsburg","date":"2026-10-10","score_ft":[2,1],"status":"FINISHED"}]}]
        result=diagnose(self.sealed,self.bundle)
        self.assertEqual(result["reason_counts"],{"TWO_SOURCE_SCORE_AGREEMENT_CANDIDATE":1})
        self.assertFalse(result["independently_verified"])
        self.assertEqual(result["production_recommendations"],"DISABLED")
    def test_conflict_remains_quarantined(self):
        self.test_two_source_agreement_is_diagnostic_only()
        self.bundle["sources"][1]["records"][0]["score_ft"]=[1,1]
        self.assertEqual(diagnose(self.sealed,self.bundle)["reason_counts"],{"TWO_SOURCE_SCORE_CONFLICT":1})
    def test_date_mismatch_does_not_link(self):
        self.bundle["sources"]=[{"provider":"OpenFootball","records":[{"home":"FC Bayern München","away":"FC Augsburg","date":"2026-10-11","score_ft":[2,1],"status":"FINISHED"}]}]
        self.assertEqual(diagnose(self.sealed,self.bundle)["reason_counts"],{"NO_MATCHING_SOURCE_DATE":1})
    def test_unsafe_input_rejected(self):
        self.bundle["independently_verified"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_SOURCE_BUNDLE"):
            diagnose(self.sealed,self.bundle)

if __name__=="__main__":unittest.main()
