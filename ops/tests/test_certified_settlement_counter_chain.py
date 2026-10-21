"""Unverified counters cannot satisfy an authenticated settlement requirement.

These are forged-input regression cases, not certified football samples. No
source fetch or cryptographic-verification fixture supplies an admission path.
"""
import copy
from datetime import datetime, timezone
import unittest

from ops.evidence_readiness_inventory import inventory
from ops.private_artifact_guard import sanitize
from ops.recommendation_readiness import grounded_progress
from ops.unified_evidence_manifest import manifest


NOW = datetime(2026, 10, 21, 13, tzinfo=timezone.utc)
STAMP = '2026-10-21T12:00:00Z'


def rows(count, claim=False):
    return [{'key': 'forged-' + str(index), 'league': 'bundesliga',
             'kickoff_utc': '2026-10-20T18:30:00Z',
             'fixture_result_source_independently_verified': claim}
            for index in range(count)]


def sources(count=300, claim=False):
    market = {'as_of_utc': STAMP, 'status': 'RESEARCH_ONLY',
              'event_count': 100, 'leagues': [{'league': 'bundesliga'}]}
    quality = {'captured_utc': STAMP, 'passed': 7, 'total': 7,
               'checks': [{'state': 'PASS'} for _ in range(7)]}
    progress = grounded_progress({'samples': rows(count, claim)}, quality, {}, market)
    summary = sanitize({'generated_utc': STAMP, 'input_status': 'CONNECTED'},
                       {'grounded_progress': progress})
    return market, quality, progress, summary


def aggregate(count=300, requirement=300):
    return {'captured_utc': STAMP, 'evidence_progress': {
        'settled_cases_in_archive': count,
        'settled_cases_required': requirement,
        'independently_verified_result_cases': count}}


def readiness(count=300, requirement=300):
    return {'independently_verified_settlements': count,
            'required_independent_settlements': requirement,
            'ready_for_production': False,
            'production_recommendations': 'DISABLED', 'blockers': []}


def unified(report):
    return manifest([], [], {'status': 'HOLD', 'accepted': 0,
                            'production_recommendations': 'DISABLED'}, report)


class CertifiedCounterChainTests(unittest.TestCase):
    def assert_not_certified(self, report):
        self.assertEqual(report['independently_verified_settlements'], 0)
        self.assertEqual(report['required_independent_settlements'], 300)
        self.assertEqual(report['remaining_independent_settlements'], 300)
        self.assertIn('INSUFFICIENT_INDEPENDENT_SETTLEMENTS', report['blockers'])
        self.assertFalse(report['ready_for_production'])
        self.assertEqual(report['production_recommendations'], 'DISABLED')

    def test_research_archive_retains_descriptive_counts_without_certification(self):
        market, quality, progress, summary = sources(45)
        self.assertEqual(progress['settled_cases_in_archive'], 45)
        self.assertEqual(summary['evidence_progress']['settled_cases_in_archive'], 45)
        report = inventory(market, summary, quality, now=NOW)
        self.assert_not_certified(report)
        self.assertEqual(report['settled_archive_candidates'], 45)

    def test_300_self_reported_flags_cannot_reduce_certified_gap_through_chain(self):
        market, quality, progress, summary = sources(claim=True)
        report = inventory(market, summary, quality, now=NOW)
        self.assertEqual(progress['independently_verified_result_cases'], 0)
        self.assertEqual(progress['result_rows_marked_independently_verified'], 300)
        self.assertEqual(summary['evidence_progress']['independently_verified_result_cases'], 0)
        self.assertEqual(summary['evidence_progress']['result_rows_marked_independently_verified'], 300)
        self.assert_not_certified(report)
        self.assertEqual(report['result_rows_marked_independently_verified'], 300)
        result = unified(report)
        self.assertEqual(result['independently_authenticated_settlements'], 0)
        self.assertEqual(result['remaining_independent_settlements'], 300)
        self.assertIn('INSUFFICIENT_INDEPENDENT_SETTLEMENTS', result['readiness_blockers'])

    def test_legacy_summary_positive_counter_is_only_an_unverified_claim(self):
        market, quality, _, _ = sources()
        report = inventory(market, aggregate(), quality, now=NOW)
        self.assert_not_certified(report)
        self.assertEqual(report['result_rows_marked_independently_verified'], 300)

    def test_manifest_cannot_propagate_legacy_counter_or_missing_blockers_as_certification(self):
        result = unified(readiness())
        self.assertEqual(result['independently_verified_settlements_reported'], 300)
        self.assertEqual(result['independently_authenticated_settlements'], 0)
        self.assertEqual(result['remaining_independent_settlements'], 300)
        self.assertIn('INSUFFICIENT_INDEPENDENT_SETTLEMENTS', result['readiness_blockers'])

    def test_each_consumer_rejects_a_caller_selected_requirement(self):
        market, quality, _, _ = sources()
        for requirement in (0, 1, 299, 301, True, False, '300', 300.0, None):
            with self.subTest(requirement=requirement, consumer='inventory'):
                with self.assertRaises(ValueError):
                    inventory(market, aggregate(requirement=requirement), quality, now=NOW)
            with self.subTest(requirement=requirement, consumer='manifest'):
                with self.assertRaises(ValueError):
                    unified(readiness(requirement=requirement))

    def test_duplicate_flags_and_truthy_values_never_create_authenticated_cases(self):
        samples = rows(1, True)
        samples.extend(copy.deepcopy(samples) * 3)
        for index, claim in enumerate((False, 1, 'true', None, {}, []), start=1):
            samples.extend(rows(1, claim))
            samples[-1]['key'] = 'other-' + str(index)
        progress = grounded_progress({'samples': samples}, {}, {}, {})
        self.assertEqual(progress['settled_cases_in_archive'], 7)
        self.assertEqual(progress['result_rows_marked_independently_verified'], 1)
        self.assertEqual(progress['independently_verified_result_cases'], 0)

    def test_caller_crypto_and_reviewer_labels_cannot_certify_aggregate(self):
        market, quality, _, _ = sources()
        summary = aggregate()
        summary.update(signature_identity_and_subject_verified=True,
                       external_provenance_rechecked=True,
                       independent_verification_authenticated=True,
                       artifact_sha256='a' * 64,
                       reviewed_by='external-reviewer')
        summary['evidence_progress']['signature_verified'] = True
        report = inventory(market, summary, quality, now=NOW)
        self.assert_not_certified(report)
        report.update(signature_identity_and_subject_verified=True,
                      independent_verification_authenticated=True,
                      authenticated_evidence_reviewed=True,
                      artifact_sha256='b' * 64)
        result = unified(report)
        self.assertEqual(result['independently_authenticated_settlements'], 0)
        self.assertEqual(result['remaining_independent_settlements'], 300)

    def test_malformed_legacy_counters_are_rejected_at_both_boundaries(self):
        market, quality, _, _ = sources()
        for count in (-1, True, False, '300', 300.0, None, [], {}):
            with self.subTest(count=count, consumer='inventory'):
                report = aggregate()
                report['evidence_progress']['independently_verified_result_cases'] = count
                with self.assertRaises(ValueError):
                    inventory(market, report, quality, now=NOW)
            with self.subTest(count=count, consumer='manifest'):
                with self.assertRaises(ValueError):
                    unified(readiness(count=count))

    def test_aggregate_counter_larger_than_recorded_archive_is_still_rejected(self):
        market, quality, _, _ = sources()
        summary = aggregate()
        summary['evidence_progress']['independently_verified_result_cases'] = 301
        with self.assertRaises(ValueError):
            inventory(market, summary, quality, now=NOW)


if __name__ == '__main__':
    unittest.main()
