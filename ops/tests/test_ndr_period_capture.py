"""New period parsing needs a new capture policy; old seals keep old meaning.

Permanent files below are original test inputs, not a new signature check or
independently certified football results. All HTTP is replaced by those bytes.
"""
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
from ops.tests import test_ndr_capture_pack as fixtures


NOW = datetime(2026, 10, 21, 8, tzinfo=timezone.utc)
POLICY = 'NDR_REGULATION_EVENT_ICONS_V2'
LEGACY = 'NDR_COMPLETION_DISPLAY_V1'
REPORT_V3 = 'football-king-ndr-completion-observations-v3'
MANIFEST_V3 = 'football-king-ndr-completion-raw-evidence-v3'
SELECTED = ['5946', '5972', '5988']


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def original():
    path = (Path(__file__).resolve().parents[2] /
            'ndr_capture_provenance/2026/10/21/39534272252-1/ndr-capture.tar.gz')
    with gzip.GzipFile(fileobj=io.BytesIO(path.read_bytes())) as stream:
        raw = stream.read(16_000_001)
    if len(raw) > 16_000_000:
        raise ValueError('OVERSIZED_TEST_ORIGINAL')
    return raw, fixtures.unpack(raw)


class NDRPeriodCaptureTests(unittest.TestCase):
    def held(self, value):
        self.assertEqual(value['status'], 'HOLD')
        self.assertEqual(value['production_recommendations'], 'DISABLED')
        if 'candidate_only' in value:
            self.assertIs(value['candidate_only'], True)
        for field in ['independently_verified', 'eligible_for_model_scoring']:
            self.assertIs(value[field], False, field)
        for field in ['formal_eligible', 'completion_authenticated', 'period_authenticated']:
            if field in value:
                self.assertIs(value[field], False, field)
        for field in ['score_ft', 'ft', 'y', 'kickoff_utc', 'result_verified']:
            self.assertNotIn(field, value)

    def fresh(self, *, edit=None):
        _, old = original()
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = root / 'index', root / 'completion'
            index.mkdir()
            (index / 'manifest.json').write_bytes(old['index-manifest.json'])
            (index / 'ndr.html').write_bytes(old['ndr.html'])

            def fetch(url):
                fixture = url.rsplit('-', 1)[1].removesuffix('.html')
                calls.append(fixture)
                body = old['ndr-detail-' + fixture + '.html']
                if edit is not None and fixture == '5988':
                    body = edit(body)
                return body, 200, 'text/html', url

            with patch('ops.ndr_completion_collector.fetch_detail', side_effect=fetch):
                report = collect(index, completion, now=NOW, limit=3)
            target = root / 'ndr-capture.tar'
            summary = prepare(index, completion, target, now=NOW)
            raw = target.read_bytes()
        self.assertEqual(calls, SELECTED)
        return raw, report, summary

    def test_original_v2_seal_replays_identical_summary_and_quarantine(self):
        raw, files = original()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
                         '52d5fe8019f981c7d60f82639177906d426f401f3c499406424272d61f00c283')
        self.assertEqual(hashlib.sha256(files['ndr-detail-5988.html']).hexdigest(),
                         '1d6af817ecf2c48700056d2c2d4d43e75fdef755cc77b3e7554cdaed124e0b0b')
        summary = validate_capture(raw, now=NOW)
        canonical = json.dumps(summary, sort_keys=True, separators=(',', ':')).encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),
                         '352205b9d60ee523a05236bf4d0cdeb4976be424f9fb3702f485f99df38442fe')
        report = json.loads(files['report.json'])
        self.assertEqual(summary['observation_count'], 2)
        self.assertEqual(summary['selection']['selected_fixture_ids'], SELECTED)
        self.assertEqual(report['rejections'], [{'provider_fixture_id': '5988',
                                                'reason': 'NON_REGULATION_NDR_EVENT_MARKER'}])
        for value in [report, json.loads(files['completion-manifest.json']), summary]:
            self.assertNotIn('parser_policy', value)
        self.held(summary)

    def test_fresh_v3_replays_same_raw_and_three_uncertified_observations(self):
        raw, report, summary = self.fresh()
        _, old = original()
        files = fixtures.unpack(raw)
        manifest = json.loads(files['completion-manifest.json'])
        self.assertEqual(report['schema'], REPORT_V3)
        self.assertEqual(manifest['schema'], MANIFEST_V3)
        self.assertEqual(summary['completion_schema'], REPORT_V3)
        for value in [report, manifest, summary]:
            self.assertEqual(value['parser_policy'], POLICY)
            self.held(value)
        self.assertEqual(report['selection'], json.loads(old['report.json'])['selection'])
        self.assertEqual(report['requests_attempted'], 3)
        self.assertEqual(report['rejections'], [])
        self.assertEqual(summary['observation_count'], 3)
        self.assertEqual([item['provider_fixture_id'] for item in report['observations']], SELECTED)
        for item in report['observations']:
            self.held(item)
            self.assertEqual(item['parser_policy'], POLICY)
        for name in ['ndr.html'] + ['ndr-detail-' + value + '.html' for value in SELECTED]:
            self.assertEqual(files[name], old[name])
        self.assertEqual(validate_capture(raw, witness=NOW, now=NOW), summary)

    def test_v3_mutually_forged_missing_legacy_or_unknown_policy_is_rejected(self):
        raw, _, _ = self.fresh()
        for policy in [None, LEGACY, 'UNKNOWN_POLICY', POLICY.lower(), True, 2, [], {}]:
            with self.subTest(policy=policy):
                files = fixtures.unpack(raw)
                for name in ['report.json', 'completion-manifest.json']:
                    value = json.loads(files[name])
                    if policy is None:
                        value.pop('parser_policy', None)
                    else:
                        value['parser_policy'] = copy.deepcopy(policy)
                    files[name] = encoded(value)
                with self.assertRaises(ValueError):
                    validate_capture(fixtures.repack(files), now=NOW)

    def test_v3_report_manifest_policy_conflicts_and_mixed_schema_are_rejected(self):
        raw, _, _ = self.fresh()
        for target in ['report.json', 'completion-manifest.json']:
            for mutation in ['policy', 'v2', 'v99']:
                with self.subTest(target=target, mutation=mutation):
                    files = fixtures.unpack(raw)
                    value = json.loads(files[target])
                    if mutation == 'policy':
                        value['parser_policy'] = LEGACY
                    else:
                        value['schema'] = value['schema'].rsplit('-v', 1)[0] + '-' + mutation
                    files[target] = encoded(value)
                    with self.assertRaises(ValueError):
                        validate_capture(fixtures.repack(files), now=NOW)

    def test_old_seal_cannot_opt_into_new_policy_or_new_schema(self):
        raw, _ = original()
        for mutation in ['policy', 'promote']:
            with self.subTest(mutation=mutation):
                files = fixtures.unpack(raw)
                for name, schema in [('report.json', REPORT_V3),
                                     ('completion-manifest.json', MANIFEST_V3)]:
                    value = json.loads(files[name])
                    value['parser_policy'] = POLICY
                    if mutation == 'promote':
                        value['schema'] = schema
                    files[name] = encoded(value)
                with self.assertRaises(ValueError):
                    validate_capture(fixtures.repack(files), now=NOW)

    def test_explicit_shootout_label_still_quarantines_fresh_v3_capture(self):
        def shootout(raw):
            marker = 'Tor durch Strafstoß (Elfmeter/Penalty/7-Meter etc.)'.encode()
            self.assertIn(marker, raw)
            return raw.replace(marker, b'Elfmeterschie&#223;en')

        raw, report, summary = self.fresh(edit=shootout)
        self.assertEqual(report['schema'], REPORT_V3)
        self.assertEqual(summary['observation_count'], 2)
        self.assertEqual(report['rejections'], [{'provider_fixture_id': '5988',
                                                'reason': 'NON_REGULATION_NDR_EVENT_MARKER'}])
        self.assertEqual(validate_capture(raw, witness=NOW, now=NOW), summary)
        self.held(summary)


if __name__ == '__main__':
    unittest.main()
