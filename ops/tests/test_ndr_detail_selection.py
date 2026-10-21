"""Deterministic coverage schedules are not successful fetches or verified FT."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import unittest

from ops.ndr_detail_selection import MAX_COHORT, ORDER, POLICY, select_rows


def cohort(size):
    return [{'provider_fixture_id': str(i)} for i in range(1, size + 1)]


class NDRDetailSelectionTests(unittest.TestCase):
    def test_known_ordinal_numeric_order_and_exact_metadata(self):
        rows = [{'provider_fixture_id': value} for value in ['100', '2', '10', '1', '9']]
        selected, plan = select_rows(rows, captured_utc='0001-01-01T12:00:00Z', limit=3)
        self.assertEqual([row['provider_fixture_id'] for row in selected], ['10', '100', '1'])
        self.assertEqual(plan, {
            'policy': POLICY, 'order': ORDER, 'day_utc': '0001-01-01',
            'request_limit': 3, 'cohort_count': 5,
            'cohort_sha256': hashlib.sha256(b'["1","2","9","10","100"]').hexdigest(),
            'start_index': 3, 'selected_fixture_ids': ['10', '100', '1'],
        })
        self.assertEqual(POLICY, 'UTC_DAY_CYCLIC_NUMERIC_FIXTURE_IDS_V1')
        self.assertEqual(ORDER, 'NUMERIC_PROVIDER_FIXTURE_ID_ASCENDING')

    def test_stable_cohort_scheduled_within_bounded_consecutive_days(self):
        start = datetime(2026, 12, 30, 23, 59, tzinfo=timezone.utc)
        for size in range(1, 41):
            for limit in [1, 2, 3]:
                with self.subTest(size=size, limit=limit):
                    selected_ids = set()
                    for day in range((size + limit - 1) // limit):
                        selected, plan = select_rows(cohort(size),
                            captured_utc=start + timedelta(days=day), limit=limit)
                        batch = [row['provider_fixture_id'] for row in selected]
                        self.assertEqual(len(batch), min(limit, size))
                        self.assertEqual(len(set(batch)), len(batch))
                        self.assertEqual(batch, plan['selected_fixture_ids'])
                        selected_ids.update(batch)
                    self.assertEqual(selected_ids, {str(i) for i in range(1, size + 1)})

    def test_same_utc_day_retries_and_index_reordering_do_not_advance_batch(self):
        rows = cohort(7)
        first = select_rows(rows, captured_utc='2026-10-21T00:00:00Z', limit=3)
        repeated = select_rows(list(reversed(rows)), captured_utc='2026-10-21T23:59:59.999999+00:00', limit=3)
        self.assertEqual(first, repeated)

    def test_scores_names_dates_and_outcomes_do_not_choose_fixtures(self):
        rows = cohort(7)
        _, first = select_rows(rows, captured_utc='2026-10-21T01:00:00Z', limit=3)
        for i, row in enumerate(rows):
            row.update(display_score={'home': i, 'away': 7-i}, date_local='2000-01-01',
                       home='changed', forecast_won=(i % 2 == 0), fetch_failed=True)
        _, after = select_rows(rows, captured_utc='2026-10-21T01:00:00Z', limit=3)
        self.assertEqual(first, after)

    def test_empty_and_smaller_than_limit_never_duplicate_or_divide_by_zero(self):
        for size in [0, 1, 2]:
            selected, plan = select_rows(cohort(size), captured_utc='2026-10-21T00:00:00Z', limit=3)
            self.assertEqual(len(selected), size)
            self.assertEqual(len(set(plan['selected_fixture_ids'])), size)
            self.assertEqual(plan['cohort_count'], size)
            if size == 0:
                self.assertEqual(plan['start_index'], 0)
                self.assertEqual(plan['cohort_sha256'], hashlib.sha256(b'[]').hexdigest())

    def test_utc_boundary_changes_day_and_next_batch(self):
        before = select_rows(cohort(7), captured_utc='2026-12-31T23:59:59.999999Z', limit=3)[1]
        after = select_rows(cohort(7), captured_utc='2027-01-01T00:00:00Z', limit=3)[1]
        self.assertEqual((before['day_utc'], after['day_utc']), ('2026-12-31', '2027-01-01'))
        self.assertNotEqual(before['selected_fixture_ids'], after['selected_fixture_ids'])

    def test_invalid_clock_limit_row_and_identity_rejected(self):
        for stamp in [None, True, datetime(2026, 10, 21),
                      datetime(2026, 10, 21, tzinfo=timezone(timedelta(hours=8))),
                      '2026-10-21', '2026-10-21T00:00:00+08:00',
                      '2026-02-30T00:00:00Z', '2026-10-21 00:00:00Z']:
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                select_rows(cohort(7), captured_utc=stamp, limit=3)
        for limit in [True, False, 0, 4, -1, '3', 1.0, None]:
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                select_rows(cohort(7), captured_utc='2026-10-21T00:00:00Z', limit=limit)
        for rows in [None, {}, (), [None], [{'provider_fixture_id': 1}],
                     [{'provider_fixture_id': True}], [{'provider_fixture_id': '0'}],
                     [{'provider_fixture_id': '01'}], [{'provider_fixture_id': '-1'}],
                     [{'provider_fixture_id': '1.0'}], [{'provider_fixture_id': '12345678901'}],
                     [{'provider_fixture_id': '1'}, {'provider_fixture_id': '1'}],
                     cohort(MAX_COHORT + 1)]:
            with self.subTest(rows_type=type(rows)), self.assertRaises(ValueError):
                select_rows(rows, captured_utc='2026-10-21T00:00:00Z', limit=3)

    def test_plan_does_not_mutate_original_rows_and_is_json_only_metadata(self):
        rows = cohort(7)
        before = copy.deepcopy(rows)
        selected, plan = select_rows(rows, captured_utc='2026-10-21T00:00:00Z', limit=3)
        self.assertEqual(rows, before)
        self.assertTrue(all(any(item is original for original in rows) for item in selected))
        self.assertEqual(json.loads(json.dumps(plan)), plan)
        self.assertFalse(any('verified' in name or 'authenticated' in name for name in plan))


if __name__ == '__main__':
    unittest.main()
