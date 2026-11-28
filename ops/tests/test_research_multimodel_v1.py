import unittest
from ops.research_multimodel_v1 import (score_matrix,dixon_coles,probabilities,
                                        multiclass_brier,log_loss,research_gate)

class MultiModelResearchTests(unittest.TestCase):
    def test_normalization(self):
        for matrix in (score_matrix(1.6,1.1),dixon_coles(1.6,1.1)):
            self.assertAlmostEqual(sum(map(sum,matrix)),1)
            self.assertAlmostEqual(sum(probabilities(matrix).values()),1)
    def test_symmetric(self):
        p=probabilities(score_matrix(1.2,1.2))
        self.assertAlmostEqual(p["home"],p["away"])
    def test_dc_changes_draw(self):
        self.assertNotEqual(probabilities(score_matrix(1.4,1.0))["draw"],
                            probabilities(dixon_coles(1.4,1.0))["draw"])
    def test_invalid(self):
        for x in (-1,0,float("nan"),float("inf")):
            with self.assertRaises(ValueError): score_matrix(x,1)
        with self.assertRaises(ValueError): dixon_coles(1,1,rho=0.5)
    def test_metrics(self):
        p={"home":0.5,"draw":0.3,"away":0.2}
        self.assertAlmostEqual(multiclass_brier(p,"home"),0.38)
        self.assertAlmostEqual(log_loss(p,"home"),0.6931471805599453)
    def test_fail_closed(self):
        self.assertEqual(research_gate()["status"],"HOLD")
        self.assertEqual(research_gate(independent_oos=True,verified_sources=True,
                         executable_quote=True,calibrated=True)["production_recommendations"],"DISABLED")

if __name__=="__main__": unittest.main()
