import unittest
from ops.v9_unified_probability import base_grid,reconcile,mass,distribution_metrics
from ops.v5_integration_acceptance import project

class UnifiedProbabilityTests(unittest.TestCase):
    def test_exact_mass_and_conditional_shape(self):
        g=base_grid(1.8,1.1);p=[.4,.35,.25];q=reconcile(g,p)
        for x,y in zip(mass(q),p):self.assertAlmostEqual(x,y,places=12)
        self.assertAlmostEqual(q[1,0]/q[2,0],g[1,0]/g[2,0])
        self.assertAlmostEqual(q[0,0]/q[1,1],g[0,0]/g[1,1])
    def test_asian_settlement_consistency(self):
        q=reconcile(base_grid(1.8,1.1),[.4,.35,.25])
        h=project(q,"handicap","home",-.25);a=project(q,"handicap","away",.25)
        self.assertAlmostEqual(h["FULL_WIN"],.4)
        self.assertAlmostEqual(h["HALF_LOSS"],.35)
        self.assertAlmostEqual(h["FULL_LOSS"],.25)
        self.assertAlmostEqual(a["HALF_WIN"],h["HALF_LOSS"])
        for line in (2.,2.25,2.5,2.75):
            over=project(q,"totals","over",line);under=project(q,"totals","under",line)
            self.assertAlmostEqual(sum(over.values()),1)
            self.assertAlmostEqual(over["HALF_WIN"],under["HALF_LOSS"])
    def test_no_new_support_and_invalid_mass(self):
        with self.assertRaisesRegex(ValueError,"UNSUPPORTED"):reconcile({(0,0):1.},[.2,.6,.2])
        with self.assertRaisesRegex(ValueError,"SCORE_MASS"):reconcile({(0,0):.4},[0.,1.,0.])
        g=reconcile(base_grid(.1,5.5),[0.,1.,0.])
        self.assertAlmostEqual(mass(g)[1],1)
        self.assertEqual(mass(g)[0],0)
    def test_score_metrics_and_identity(self):
        g=base_grid(1.2,1.4);q=reconcile(g,mass(g))
        for k in g:self.assertAlmostEqual(g[k],q[k],places=12)
        m=distribution_metrics([{"grid":q,"actual":(1,1),"y":1}])
        self.assertGreater(m["exact_score_log_loss"],0)
        self.assertEqual(len(m["hypothetical_lines"]),5)
