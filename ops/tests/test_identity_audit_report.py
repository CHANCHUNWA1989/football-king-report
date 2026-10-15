"""Regression checks for archived fixture identity auditing."""
import unittest
from fixture_identity_audit import conflicting_fixture_ids, identity_audit_report

class IdentityAuditTests(unittest.TestCase):
    def test_same_match_rows_are_allowed(self):
        record=dict(fixture_id="one",kickoff_utc="2026-10-15T18:00:00Z",home="A",away="B")
        self.assertEqual(conflicting_fixture_ids([record,record]),[])

    def test_different_match_same_id_is_conflict(self):
        record=dict(fixture_id="one",kickoff_utc="2026-10-15T18:00:00Z",home="A",away="B")
        other=dict(record,away="C")
        report=identity_audit_report([record,other])
        self.assertEqual(report["conflicting_fixture_id_count"],1)
        self.assertFalse(report["independently_verified"])

if __name__=="__main__":
    unittest.main()
