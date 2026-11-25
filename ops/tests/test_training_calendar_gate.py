import unittest
from ops.training_calendar_gate import audit

class CoverageTests(unittest.TestCase):
    def test_partial_data(self):
        ref=[str(i) for i in range(200)]
        r=audit(ref,ref[:116]); self.assertEqual(r['coverage_fraction'],.58)
        self.assertEqual(r['unmatched_reference_count'],84)
        self.assertFalse(r['reference_coverage_threshold_met'])
    def test_threshold_does_not_admit(self):
        ref=[str(i) for i in range(100)]
        r=audit(ref,ref[:95]); self.assertTrue(r['reference_coverage_threshold_met'])
        self.assertFalse(r['training_admission_authorized']);self.assertEqual(r['status'],'HOLD')
    def test_complete_still_hold(self):
        r=audit(['a'],['a']);self.assertEqual(r['coverage_fraction'],1)
        self.assertFalse(r['independent_result_certification'])
    def test_empty(self):
        self.assertIsNone(audit([],[])['coverage_fraction'])
    def test_duplicates(self):
        for a,b in [(['a','a'],['a']),(['a'],['a','a'])]:
            with self.assertRaisesRegex(ValueError,'DUPLICATE'):audit(a,b)
    def test_unmatched(self):
        with self.assertRaisesRegex(ValueError,'OUTSIDE'):audit(['a'],['b'])
    def test_invalid(self):
        for a,b in [({},[]),([''],[]),(['a'],[True]),(['a']*3001,[])]:
            with self.assertRaisesRegex(ValueError,'INVALID'):audit(a,b)
    def test_deterministic_missing(self):
        self.assertEqual(audit(['z','a','b'],['b'])['missing_reference_ids'],['a','z'])
