import unittest
from integrated_research_report import build_report

class IntegratedResearchTests(unittest.TestCase):
    def test_empty_research_remains_disabled(self):
        diagnostic={"schema":"football-king-cross-source-ft-diagnostic-v1",
                    "independently_verified":False,
                    "external_provenance_rechecked":False,
                    "production_recommendations":"DISABLED",
                    "agreements":[]}
        report=build_report([],diagnostic)
        self.assertEqual(report["candidate_links"],0)
        self.assertEqual(report["settlement_coverage"]["remaining"],300)
        self.assertEqual(report["production_recommendations"],"DISABLED")
        self.assertFalse(report["eligible_for_model_scoring"])

if __name__=="__main__":
    unittest.main()
