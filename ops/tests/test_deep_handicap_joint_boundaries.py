import unittest
from decimal import Decimal,localcontext
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deep_handicap_joint_score import project,_project_score,_total_units
from deep_handicap_diagnostics import _joint
from asian_handicap_research import TYPES

class JointProjectionBoundaryTests(unittest.TestCase):
    def test_exact_total_quarter_under_low_decimal_precision(self):
        with localcontext() as ctx:
            ctx.prec=5
            self.assertEqual(_total_units(Decimal("3.25")),13)
            for line in ("3.250000000000000000000001","3.24999999999999999999999",True):
                with self.assertRaises(ValueError):
                    _total_units(line)
    def test_projection_rejects_invalid_mass_cells_and_bool_units(self):
        for pmf in ({(1,0):.9},{(1,0):float("nan")},{(1,0):1.1,(0,0):-.1},{(True,0):1.0}):
            with self.assertRaises(ValueError):
                _project_score(pmf,"HOME",-9,13,1.0)
        with self.assertRaises(ValueError):
            _project_score({(1,0):1.0},"HOME",-9,True,1.0)
    def test_separate_projection_matches_legacy_grade_without_replacing_it(self):
        for pace in (.65,.85,1.0):
            old=_joint(2.9,.9,"HOME",-2.25,pace)
            new=project(2.9,.9,"HOME",-2.25,3.25,pace=pace)
            self.assertTrue(new["legacy_capture_model_unchanged"])
            self.assertEqual(new["calculation_version"],"dhe-joint-score-projection-v1")
            for k in TYPES:
                self.assertAlmostEqual(old["grades"][k],new["handicap"][k],places=10)
            self.assertEqual(new["production_recommendations"],"DISABLED")
