"""Synthetic receipt replay tests; consistency is never result certification."""
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from ops import raw_origin_metadata as metadata
from ops import shadow_raw_source_collector as collector


NOW = datetime(2026, 10, 20, 10, tzinfo=timezone.utc)


def response(url):
    raw = b'[]' if url.startswith('https://api.openligadb.de/') else b'{"matches":[]}'
    return raw, 200, 'application/json', url


class RawOriginMetadataTests(unittest.TestCase):
    def setUp(self):
        with tempfile.TemporaryDirectory() as folder:
            self.manifest = collector.collect(2026, folder, getter=response, now=NOW)

    def check(self, manifest=None, **kwargs):
        return metadata.validate_manifest(self.manifest if manifest is None else manifest,
                                          now=kwargs.pop('now', NOW), **kwargs)

    def changed(self, path, value):
        manifest = copy.deepcopy(self.manifest)
        node = manifest
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        return manifest

    def test_exact_v2_success_is_structural_only(self):
        self.assertIsNone(self.check())
        self.assertEqual(self.manifest['status'], 'HOLD')
        self.assertEqual(self.manifest['production_recommendations'], 'DISABLED')
        for key in ['independently_verified', 'eligible_for_model_scoring']:
            self.assertIs(self.manifest[key], False)

    def test_legacy_v1_or_extra_trust_claims_cannot_be_upgraded(self):
        cases = [self.changed(['schema'], metadata.LEGACY_SCHEMA),
                 self.changed(['schema'], 'football-king-raw-ft-source-candidates-v3'),
                 self.changed(['status'], 'VERIFIED'),
                 self.changed(['production_recommendations'], 'ENABLED'),
                 self.changed(['independently_verified'], True),
                 self.changed(['independently_verified'], 0),
                 self.changed(['eligible_for_model_scoring'], True)]
        extra = copy.deepcopy(self.manifest)
        extra['source_authenticated'] = True
        cases.append(extra)
        missing = copy.deepcopy(self.manifest)
        del missing['eligible_for_model_scoring']
        cases.append(missing)
        for manifest in cases:
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                self.check(manifest)

    def test_exact_provider_count_order_and_season_replayed(self):
        cases = [None, {}, [], self.manifest['sources'][:1],
                 list(reversed(self.manifest['sources'])),
                 self.manifest['sources'] * 2, [None, None],
                 [self.manifest['sources'][0], self.manifest['sources'][0]]]
        for sources in cases:
            with self.subTest(sources=sources), self.assertRaises(ValueError):
                self.check(self.changed(['sources'], sources))
        for season in [True, False, 2026.0, '2026', None, 1999, 2101, 2025]:
            with self.subTest(season=season), self.assertRaises(ValueError):
                self.check(self.changed(['season_start'], season))

    def test_exact_endpoints_and_denied_redirects_for_both_providers(self):
        for index, source in enumerate(self.manifest['sources']):
            for key, value in [('source_url', source['source_url'] + '?alias=1'),
                               ('final_url', source['source_url'] + '/'),
                               ('redirect_policy', 'FOLLOW'),
                               ('redirect_policy', None)]:
                with self.subTest(index=index, key=key), self.assertRaises(ValueError):
                    self.check(self.changed(['sources', index, key], value))

    def test_success_raw_identity_status_and_media_are_exact(self):
        cases = [('raw_file', '../openligadb.json'), ('raw_file', 'openfootball.json'),
                 ('raw_sha256', 'A' * 64), ('raw_sha256', 'a' * 63),
                 ('raw_sha256', None), ('bytes', True), ('bytes', 1.0),
                 ('bytes', 0), ('bytes', collector.MAX_BYTES + 1),
                 ('http_status', True), ('http_status', 200.0), ('http_status', 201),
                 ('content_type', 'text/plain'), ('content_type', 'application/json; charset=utf-8'),
                 ('status', 'VERIFIED'), ('status', 'ERROR')]
        for key, value in cases:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.check(self.changed(['sources', 0, key], value))
        for extra in ['error_type', 'error_code', 'verified']:
            manifest = copy.deepcopy(self.manifest)
            manifest['sources'][0][extra] = 'caller claim'
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check(manifest)
        self.assertIsNone(self.check(self.changed(['sources', 1, 'content_type'], 'text/plain')))

    def test_all_required_receipt_fields_checked(self):
        for index, source in enumerate(self.manifest['sources']):
            for field in source:
                manifest = copy.deepcopy(self.manifest)
                del manifest['sources'][index][field]
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    self.check(manifest)

    def test_each_utc_boundary_and_serial_order_replayed(self):
        later = (NOW + timedelta(seconds=1)).isoformat()
        earlier = (NOW - timedelta(seconds=1)).isoformat()
        cases = [(['captured_utc'], later),
                 (['sources', 0, 'requested_utc'], earlier),
                 (['sources', 0, 'requested_utc'], later),
                 (['sources', 0, 'completed_utc'], earlier),
                 (['sources', 0, 'completed_utc'], later),
                 (['sources', 1, 'requested_utc'], earlier),
                 (['sources', 1, 'completed_utc'], later)]
        for path, value in cases:
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                self.check(self.changed(path, value))
        with self.assertRaisesRegex(ValueError, 'CHRONOLOGY'):
            self.check(before=NOW - timedelta(microseconds=1))
        self.assertIsNone(self.check(now=NOW + timedelta(seconds=1), before=NOW))

    def test_timestamp_requires_explicit_utc_and_valid_calendar(self):
        invalid = [None, False, 1, '', '2026-10-20', '2026-10-20T10:00:00',
                   '2026-10-20T18:00:00+08:00', '2026-10-20T10:00:00-00:00',
                   '2026-10-20T10:00:00.1234567Z', '2026-02-30T10:00:00Z',
                   '2026-10-20T25:00:00Z', '2026-10-20T10:00:60Z',
                   '2026-10-20T10:00:00Z\n']
        for value in invalid:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'UTC'):
                metadata.utc(value)
        self.assertEqual(metadata.utc('2026-10-20T10:00:00Z'), NOW)
        self.assertEqual(metadata.utc('2026-10-20T10:00:00+00:00'), NOW)

    def test_validation_clock_must_be_aware(self):
        for key in ['now', 'before']:
            for value in [False, 1, 'now', datetime(2026, 10, 20)]:
                kwargs = {key: value}
                with self.subTest(key=key, value=value), self.assertRaisesRegex(ValueError, 'CLOCK'):
                    self.check(**kwargs)
        self.assertIsNone(self.check(now=NOW.astimezone(timezone(timedelta(hours=8)))))

    def test_error_receipts_are_finite_and_never_contain_raw_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            def failed(url):
                raise TimeoutError('PRIVATE SOURCE MESSAGE')
            manifest = collector.collect(2026, folder, getter=failed, now=NOW)
        self.assertIsNone(self.check(manifest))
        original = copy.deepcopy(self.manifest)
        self.manifest = manifest
        try:
            cases = [('final_url', manifest['sources'][0]['source_url']),
                     ('error_type', 'ARBITRARY_PRIVATE_EXCEPTION'),
                     ('error_type', None), ('error_code', 'caller verified'),
                     ('http_status', True), ('http_status', '503'),
                     ('http_status', 99), ('http_status', 600)]
            for field, value in cases:
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.check(self.changed(['sources', 0, field], value))
            for field, value in [('raw_file', 'openligadb.json'), ('bytes', 1),
                                 ('raw_sha256', 'a' * 64), ('content_type', 'application/json')]:
                with self.subTest(extra=field), self.assertRaises(ValueError):
                    self.check(self.changed(['sources', 0, field], value))
            self.assertIsNone(self.check(self.changed(['sources', 0, 'http_status'], 503)))
        finally:
            self.manifest = original


if __name__ == '__main__':
    unittest.main()
