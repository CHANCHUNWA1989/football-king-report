"""Segmented replay tests reuse real-format proofs with mocked signature CLI."""
import unittest
from unittest.mock import patch
from ops.tests import test_dixon_coles_forward_replay as fixture_tests
from ops import dixon_coles_segmented_replay as segmented


class SegmentedReplayTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_tests.DixonColesForwardReplayTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def run_segments(self, captures=None):
        with patch("subprocess.run",side_effect=self.fixture.cli) as cli:
            r=segmented.audit(self.fixture.forecasts,
                              self.fixture.captures if captures is None else captures,
                              now=fixture_tests.CHECKED)
        self.fixture.assert_safe(r)
        return r,cli

    def test_equivalence_across_segments(self):
        for _ in range(3):
            self.fixture.add_capture()
        legacy,_=self.fixture.run_replay()
        with patch.object(segmented,"SEGMENT_SIZE",2):
            r,_=self.run_segments()
        self.assertTrue(r["audit_completed"],r["reason"])
        for k in ("cases","metrics","comparison","selected_cohort_sha256","capture_references"):
            self.assertEqual(r[k],legacy[k])
        self.assertEqual(r["segment_count"],2)
        self.assertEqual(r["verified_capture_count"],4)

    def test_65_distinct_captures_exceed_previous_limit(self):
        for _ in range(64):
            self.fixture.add_capture()
        r,cli=self.run_segments()
        self.assertTrue(r["audit_completed"],r["reason"])
        self.assertEqual(r["verified_capture_count"],65)
        self.assertEqual(r["segment_count"],5)
        self.assertEqual(len(r["capture_references"]),65)
        self.assertEqual(r["settled_candidate_count"],1)
        self.assertEqual(cli.call_count,68)
        self.assertFalse(r["remote_history_completeness_verified"])

    def test_cross_segment_score_conflict_quarantines(self):
        def change(row):
            row["matchResults"][0]["pointsTeam1"]=0
        self.fixture.add_capture(change=change)
        with patch.object(segmented,"SEGMENT_SIZE",1):
            r,_=self.run_segments()
        self.assertTrue(r["audit_completed"],r["reason"])
        self.assertEqual(r["quarantined_candidate_count"],1)
        self.assertEqual(r["settled_candidate_count"],0)
        self.assertIsNone(r["metrics"])

    def test_duplicate_across_segments_rejected_before_capture_calls(self):
        with patch.object(segmented,"SEGMENT_SIZE",1):
            r,cli=self.run_segments(self.fixture.captures*2)
        self.fixture.assert_no_scores(r,completed=False)
        self.assertEqual(r["reason"],"DUPLICATE_CAPTURE_RUN_ATTEMPT")
        self.assertEqual(cli.call_count,3)
        self.assertEqual(r["verified_capture_count"],0)

    def test_missing_segment_reference_rejected(self):
        real=segmented.replay._results
        def drop(entries,current,snapshots,needed):
            index,refs=real(entries,current,snapshots,needed)
            return index,refs[:-1]
        with patch.object(segmented.replay,"_results",side_effect=drop):
            r,_=self.run_segments()
        self.fixture.assert_no_scores(r,completed=False)
        self.assertEqual(r["reason"],"SEGMENT_COVERAGE_MISMATCH")

    def test_late_segment_failure_no_partial_metrics(self):
        self.fixture.add_capture()
        real=segmented.replay._results
        calls=[]
        def fail(entries,current,snapshots,needed):
            calls.append(1)
            if len(calls)==2:
                raise segmented.replay.ReplayError("FRESH_CAPTURE_VERIFICATION_FAILED")
            return real(entries,current,snapshots,needed)
        with patch.object(segmented,"SEGMENT_SIZE",1),patch.object(segmented.replay,"_results",side_effect=fail):
            r,_=self.run_segments()
        self.fixture.assert_no_scores(r,completed=False)
        self.assertEqual(r["reason"],"FRESH_CAPTURE_VERIFICATION_FAILED")
        self.assertEqual(r["verified_capture_count"],0)

    def test_global_budget_precedes_capture_verification(self):
        self.fixture.add_capture()
        size=sum((entry["proof_dir"]/name).stat().st_size for entry in self.fixture.captures
                 for name in segmented.replay.CAPTURE_FILES)
        with patch.object(segmented,"MAX_TOTAL_BYTES",size-1):
            r,cli=self.run_segments()
        self.fixture.assert_no_scores(r,completed=False)
        self.assertEqual(r["reason"],"CAPTURE_HISTORY_PAYLOAD_LIMIT")
        self.assertEqual(cli.call_count,3)

    def test_global_count_bound(self):
        r,cli=self.run_segments(self.fixture.captures*(segmented.MAX_TOTAL_CAPTURES+1))
        self.fixture.assert_no_scores(r,completed=False)
        self.assertEqual(r["reason"],"PROOF_COUNT_LIMIT")
        self.assertEqual(cli.call_count,0)

    def test_empty_capture_manifest(self):
        r,_=self.run_segments([])
        self.assertTrue(r["audit_completed"],r["reason"])
        self.assertEqual(r["verified_capture_count"],0)
        self.assertEqual(r["segment_count"],0)
        self.assertEqual(r["settled_candidate_count"],0)
        self.assertFalse(r["remote_history_completeness_verified"])
