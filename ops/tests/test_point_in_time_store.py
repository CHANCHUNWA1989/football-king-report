"""Synthetic fail-closed point-in-time feature admission tests; no live feeds."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from point_in_time_store import audit_cut, build_cut, verify_pinned_cut

KICKOFF = "2026-11-03T20:00:00Z"
DECISION = "2026-11-03T20:49:00Z"


def evidence(**changes):
    record = {
        "evidence_id": "score-a-1", "fixture_id": "test-fixture-001",
        "kind": "score", "source": "test-provider-a", "source_group": "upstream-a",
        "source_event_id": "provider-event-456",
        "source_updated_utc": "2026-11-03T20:44:01Z",
        "captured_utc": "2026-11-03T20:44:02Z",
        "received_utc": "2026-11-03T20:44:03Z",
        "available_utc": "2026-11-03T20:44:04Z",
        "raw_sha256": "a" * 64,
    }
    record.update(changes)
    return record


def audit(rows=None, **kw):
    opts = {"fixture_id": "test-fixture-001", "kickoff_utc": KICKOFF,
            "decision_utc": DECISION, "phase": "INPLAY"}
    opts.update(kw)
    return audit_cut(rows if rows is not None else [evidence()], **opts)


class PointInTimeStoreTests(unittest.TestCase):
    def test_good_live_cut_is_research_only_not_external_certification(self):
        result = audit()
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertEqual(result["production_recommendations"], "DISABLED")
        self.assertFalse(result["source_authenticated"])
        self.assertFalse(result["external_clock_attested"])
        self.assertFalse(result["positive_ev_verified"])
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_pre_match_cut_is_supported(self):
        row = evidence(source_updated_utc="2026-11-03T19:30:00Z",
                       captured_utc="2026-11-03T19:30:01Z",
                       received_utc="2026-11-03T19:30:02Z",
                       available_utc="2026-11-03T19:30:03Z", kind="lineup")
        self.assertEqual(audit([row], decision_utc="2026-11-03T19:40:00Z",
                               phase="PREMATCH")["status"], "RESEARCH_ONLY")

    def test_late_received_goal_rejected_despite_old_upstream_time(self):
        row = evidence(received_utc="2026-11-03T20:52:00Z",
                       available_utc="2026-11-03T20:52:01Z")
        self.assertEqual(audit([row])["reason"], "EVIDENCE_NOT_AVAILABLE_AT_DECISION")

    def test_late_xg_is_not_usable_as_old_feature(self):
        row = evidence(kind="xg", evidence_id="xg-2",
                       source_updated_utc="2026-11-03T20:45:00Z",
                       captured_utc="2026-11-03T20:45:01Z",
                       received_utc="2026-11-03T20:49:30Z",
                       available_utc="2026-11-03T20:49:31Z")
        self.assertEqual(audit([row])["status"], "HOLD")

    def test_future_provider_update_and_captured_earlier_rejected(self):
        self.assertEqual(audit([evidence(source_updated_utc="2026-11-03T20:46:00Z")])["reason"],
                         "EVIDENCE_TIME_ORDER_CONFLICT")

    def test_missing_received_clock_fails_closed(self):
        row = evidence()
        row.pop("received_utc")
        self.assertEqual(audit([row])["reason"], "INVALID_EVIDENCE_RECORD_SCHEMA")

    def test_unknown_result_or_certification_flags_rejected(self):
        for key, value in (("full_time_result", "HOME"), ("source_authenticated", True)):
            with self.subTest(key=key):
                row = evidence(**{key: value})
                self.assertEqual(audit([row])["status"], "HOLD")

    def test_mismatched_fixture_rejected(self):
        self.assertEqual(audit([evidence(fixture_id="different-match")])["reason"],
                         "FIXTURE_ID_MISMATCH")

    def test_duplicate_evidence_id_rejected(self):
        self.assertEqual(audit([evidence(), evidence()])["reason"], "DUPLICATE_EVIDENCE_ID")

    def test_empty_evidence_set_rejected(self):
        self.assertEqual(audit([])["status"], "HOLD")

    def test_invalid_digest_rejected(self):
        self.assertEqual(audit([evidence(raw_sha256="not-a-digest")])["reason"],
                         "INVALID_RAW_DIGEST")

    def test_phase_must_match_kickoff(self):
        self.assertEqual(audit(phase="PREMATCH")["reason"], "PHASE_DECISION_TIME_CONFLICT")
        self.assertEqual(audit(decision_utc="2026-11-03T19:40:00Z")["reason"],
                         "PHASE_DECISION_TIME_CONFLICT")

    def test_non_utc_offset_normalizes_to_same_fingerprint(self):
        row = evidence()
        original = audit([row])
        shifted = copy.deepcopy(row)
        shifted["source_updated_utc"] = "2026-11-04T04:44:01+08:00"
        shifted["captured_utc"] = "2026-11-04T04:44:02+08:00"
        shifted["received_utc"] = "2026-11-04T04:44:03+08:00"
        shifted["available_utc"] = "2026-11-04T04:44:04+08:00"
        self.assertEqual(original["input_sha256"], audit([shifted])["input_sha256"])

    def test_evidence_order_does_not_change_digest(self):
        second = evidence(evidence_id="score-b-2", source="source-b", source_group="upstream-b")
        self.assertEqual(audit([evidence(), second])["input_sha256"],
                         audit([second, evidence()])["input_sha256"])

    def test_tamper_changes_digest_against_external_pin(self):
        cut = audit()
        self.assertTrue(verify_pinned_cut(cut, cut["input_sha256"]))
        tampered = audit([evidence(raw_sha256="b" * 64)])
        self.assertFalse(verify_pinned_cut(tampered, cut["input_sha256"]))
        self.assertFalse(verify_pinned_cut(cut, "bad"))

    def test_no_independent_certification_from_two_websites(self):
        second = evidence(evidence_id="score-b-2", source="website-b", source_group="upstream-a")
        result = audit([evidence(), second])
        self.assertEqual(result["status"], "RESEARCH_ONLY")
        self.assertFalse(result["source_authenticated"])

    def test_naive_time_or_boolean_data_are_rejected(self):
        self.assertEqual(audit(decision_utc="2026-11-03T20:49:00")["status"], "HOLD")
        self.assertEqual(audit([evidence(raw_sha256=True)])["status"], "HOLD")

    def test_all_rows_fail_closed_when_one_record_late(self):
        late = evidence(evidence_id="quote-2", kind="quote",
                        source_updated_utc="2026-11-03T20:50:00Z",
                        captured_utc="2026-11-03T20:50:01Z",
                        received_utc="2026-11-03T20:50:02Z",
                        available_utc="2026-11-03T20:50:03Z")
        self.assertEqual(audit([evidence(), late])["status"], "HOLD")


if __name__ == "__main__":
    unittest.main()
