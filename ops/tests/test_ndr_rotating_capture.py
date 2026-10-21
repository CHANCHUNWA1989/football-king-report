"""Replay bounded day selection from original NDR bytes; never certify results."""
import copy
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ops.ndr_capture_pack import prepare, validate_capture
from ops.ndr_completion_collector import collect
from ops.ndr_detail_selection import POLICY
from ops.ndr_result_observations import SOURCE_URL
from ops.tests.test_ndr_completion_observations import detail
from ops.tests.test_ndr_result_observations import page, row
from ops.tests import test_ndr_capture_pack as capture_fixtures


NOW = datetime(2026, 10, 21, 2, 30, tzinfo=timezone.utc)
REPORT_V2 = 'football-king-ndr-completion-observations-v2'
MANIFEST_V2 = 'football-king-ndr-completion-raw-evidence-v2'


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


class NDRRotatingCaptureTests(unittest.TestCase):
    def capture(self, *, limit=3, fail_first=False, reverse_index=False):
        fixtures = ['104', '101', '107', '102', '106', '103', '105']
        if reverse_index:
            fixtures.reverse()
        teams = {fixture: (str(200 + int(fixture)), str(400 + int(fixture)))
                 for fixture in fixtures}
        body = page(''.join(row(fixture=fixture, home=teams[fixture][0],
                                away=teams[fixture][1]) for fixture in fixtures))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = root / 'index', root / 'completion'
            index.mkdir()
            manifest = {
                'schema': 'football-king-external-raw-evidence-v1',
                'captured_utc': '2026-10-20T17:00:00+00:00',
                'status': 'HOLD', 'production_recommendations': 'DISABLED',
                'independently_verified': False, 'eligible_for_model_scoring': False,
                'sources': [{'provider': 'NDR', 'source_url': SOURCE_URL,
                             'status': 'FETCHED_UNVERIFIED', 'raw_file': 'ndr.html',
                             'raw_sha256': hashlib.sha256(body).hexdigest(),
                             'bytes': len(body), 'http_status': 200,
                             'content_type': 'text/html'}]}
            (index / 'manifest.json').write_bytes(encoded(manifest))
            (index / 'ndr.html').write_bytes(body)
            calls = []

            def fetch(url):
                calls.append(url)
                if fail_first and len(calls) == 1:
                    raise TimeoutError('unsafe source exception must not become metadata')
                fixture = url.rsplit('-', 1)[1].removesuffix('.html')
                home, away = teams[fixture]
                raw = detail().replace(b'spielstatistik-5884.html',
                                       ('spielstatistik-' + fixture + '.html').encode())
                raw = raw.replace(b'mannschaftfussball264.html',
                                  ('mannschaftfussball' + home + '.html').encode())
                raw = raw.replace(b'mannschaftfussball110.html',
                                  ('mannschaftfussball' + away + '.html').encode())
                return raw, 200, 'text/html', url

            with patch('ops.ndr_completion_collector.fetch_detail', side_effect=fetch):
                report = collect(index, completion, limit=limit, now=NOW)
            subject = root / 'ndr-capture.tar'
            summary = prepare(index, completion, subject, now=NOW)
            raw = subject.read_bytes()
        return raw, report, summary, calls

    def assert_held(self, summary):
        self.assertEqual(summary['status'], 'HOLD')
        self.assertEqual(summary['production_recommendations'], 'DISABLED')
        for key in ['independently_verified', 'eligible_for_model_scoring', 'formal_eligible']:
            self.assertIs(summary[key], False)

    def test_v2_original_capture_replays_every_configured_request_limit(self):
        for limit in (1, 2, 3):
            with self.subTest(limit=limit):
                raw, report, summary, calls = self.capture(limit=limit)
                self.assertEqual(report['schema'], REPORT_V2)
                self.assertEqual(summary['completion_schema'], REPORT_V2)
                self.assertEqual(summary['selection_policy'], POLICY)
                self.assertEqual(summary['selection'], report['selection'])
                self.assertEqual(len(calls), limit)
                self.assertEqual(report['requests_attempted'], limit)
                self.assertEqual([source['provider_fixture_id'] for source in report['sources']],
                                 report['selection']['selected_fixture_ids'])
                self.assertEqual(report['observation_count'], limit)
                self.assertEqual(validate_capture(raw, witness=NOW, now=NOW), summary)
                self.assert_held(summary)

    def test_index_reordering_does_not_change_same_day_selected_fixed_ids(self):
        _, report, _, _ = self.capture()
        _, reversed_report, _, _ = self.capture(reverse_index=True)
        self.assertEqual(report['selection'], reversed_report['selection'])
        self.assertEqual([x['provider_fixture_id'] for x in report['sources']],
                         [x['provider_fixture_id'] for x in reversed_report['sources']])

    def test_failed_selected_fetch_is_replayed_without_replacement_request(self):
        raw, report, summary, calls = self.capture(fail_first=True)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(report['sources']), 3)
        self.assertEqual(report['fetch_errors'][0]['provider_fixture_id'],
                         report['selection']['selected_fixture_ids'][0])
        self.assertEqual(summary['fetch_error_count'], 1)
        self.assertEqual(summary['observation_count'], 2)
        self.assertEqual(validate_capture(raw, witness=NOW, now=NOW), summary)
        self.assert_held(summary)

    def test_every_forged_selection_field_rejected_even_when_manifest_matches(self):
        raw, _, _, _ = self.capture()
        mutations = {
            'policy': 'FIRST_THREE_ACCEPTED_INDEX_ROWS_NO_ROTATION_YET',
            'order': 'LEXICOGRAPHIC', 'day_utc': '2026-10-20',
            'request_limit': 2, 'cohort_count': 8, 'cohort_sha256': '0' * 64,
            'start_index': 999, 'selected_fixture_ids': ['104', '101', '107'],
        }
        for key, value in mutations.items():
            with self.subTest(field=key):
                files = capture_fixtures.unpack(raw)
                report = json.loads(files['report.json'])
                manifest = json.loads(files['completion-manifest.json'])
                report['selection'][key] = value
                manifest['selection'][key] = copy.deepcopy(value)
                files['report.json'], files['completion-manifest.json'] = encoded(report), encoded(manifest)
                with self.assertRaises(ValueError):
                    validate_capture(capture_fixtures.repack(files), witness=NOW, now=NOW)

    def test_selection_json_types_extra_fields_and_report_manifest_conflicts_rejected(self):
        raw, _, _, _ = self.capture()
        for field in ['request_limit', 'cohort_count', 'start_index', 'extra', 'conflict']:
            with self.subTest(field=field):
                files = capture_fixtures.unpack(raw)
                report = json.loads(files['report.json'])
                manifest = json.loads(files['completion-manifest.json'])
                if field == 'extra':
                    report['selection']['caller_cursor'] = 0
                    manifest['selection']['caller_cursor'] = 0
                elif field == 'conflict':
                    manifest['selection']['day_utc'] = '2026-10-20'
                else:
                    report['selection'][field] = True
                    manifest['selection'][field] = True
                files['report.json'], files['completion-manifest.json'] = encoded(report), encoded(manifest)
                with self.assertRaises(ValueError):
                    validate_capture(capture_fixtures.repack(files), witness=NOW, now=NOW)

    def test_partial_or_reordered_attempt_cohort_cannot_replace_selected_ids(self):
        raw, _, _, _ = self.capture()
        for mutation in ['partial', 'reordered']:
            with self.subTest(mutation=mutation):
                files = capture_fixtures.unpack(raw)
                report = json.loads(files['report.json'])
                manifest = json.loads(files['completion-manifest.json'])
                if mutation == 'partial':
                    source = report['sources'].pop()
                    report['requests_attempted'] -= 1
                    report['attempt_count'] -= 1
                    report['observations'].pop()
                    report['observation_count'] -= 1
                    del files[source['raw_file']]
                else:
                    report['sources'].reverse()
                    report['observations'].reverse()
                manifest['sources'] = copy.deepcopy(report['sources'])
                manifest['requests_attempted'] = report['requests_attempted']
                files['report.json'], files['completion-manifest.json'] = encoded(report), encoded(manifest)
                with self.assertRaises(ValueError):
                    validate_capture(capture_fixtures.repack(files), witness=NOW, now=NOW)

    def test_schema_downgrade_mismatch_and_unknown_version_are_rejected(self):
        raw, _, _, _ = self.capture()
        for mutation in ['downgrade', 'mismatch', 'unknown']:
            with self.subTest(mutation=mutation):
                files = capture_fixtures.unpack(raw)
                report = json.loads(files['report.json'])
                manifest = json.loads(files['completion-manifest.json'])
                if mutation == 'unknown':
                    report['schema'] = REPORT_V2.replace('-v2', '-v3')
                    manifest['schema'] = MANIFEST_V2.replace('-v2', '-v3')
                else:
                    report['schema'] = REPORT_V2.replace('-v2', '-v1')
                    if mutation == 'downgrade':
                        manifest['schema'] = MANIFEST_V2.replace('-v2', '-v1')
                        report.pop('selection')
                        manifest.pop('selection')
                files['report.json'], files['completion-manifest.json'] = encoded(report), encoded(manifest)
                with self.assertRaises(ValueError):
                    validate_capture(capture_fixtures.repack(files), witness=NOW, now=NOW)

    def test_legacy_permanent_original_replays_without_new_selection_fields(self):
        root = Path(__file__).resolve().parents[2]
        archive = root / 'ndr_capture_provenance/2026/10/20/39464601097-1/ndr-capture.tar.gz'
        with gzip.GzipFile(fileobj=io.BytesIO(archive.read_bytes())) as stream:
            raw = stream.read(16_000_001)
        self.assertLessEqual(len(raw), 16_000_000)
        summary = validate_capture(raw, witness=datetime(2026, 10, 20, 17, 17, 9, tzinfo=timezone.utc), now=NOW)
        self.assertEqual(summary['requests_attempted'], 3)
        self.assertEqual(summary['observation_count'], 3)
        for key in ['completion_schema', 'selection_policy', 'selection']:
            self.assertNotIn(key, summary)
        self.assert_held(summary)


if __name__ == '__main__':
    unittest.main()
