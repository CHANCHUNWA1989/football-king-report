"""Capture replay verifies quarantined content without authenticating results."""
import copy
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from ops.ndr_capture_pack import prepare, validate_capture
from ops.ndr_completion_collector import collect
from ops.ndr_result_observations import SOURCE_URL
from ops.tests.test_ndr_completion_observations import detail
from ops.tests.test_ndr_result_observations import page, row

NOW = datetime(2026, 10, 19, 8, tzinfo=timezone.utc)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def unpack(raw):
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        return {item.name: archive.extractfile(item).read() for item in archive.getmembers()}


def repack(files, extra=None):
    output = io.BytesIO()
    order = ['index-manifest.json', 'ndr.html', 'completion-manifest.json', 'report.json']
    order += sorted(name for name in files if name.startswith('ndr-detail-'))
    order += sorted(set(files) - set(order))
    with tarfile.open(fileobj=output, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name in order:
            if name not in files:
                continue
            info = tarfile.TarInfo(name)
            info.mode, info.size = 0o600, len(files[name])
            archive.addfile(info, io.BytesIO(files[name]))
        if extra is not None:
            archive.addfile(extra)
    return output.getvalue()


class NDRCapturePackTests(unittest.TestCase):
    def make(self, root, *, rows=None, bodies=None, missing=False, rejected=False):
        index, completion = root / 'index', root / 'completion'
        index.mkdir()
        raw = page(rows)
        manifest = {
            'schema': 'football-king-external-raw-evidence-v1',
            'captured_utc': (NOW - timedelta(minutes=5)).isoformat(),
            'status': 'HOLD', 'production_recommendations': 'DISABLED',
            'independently_verified': False, 'eligible_for_model_scoring': False,
            'sources': [] if missing else [{
                'provider': 'NDR', 'source_url': SOURCE_URL,
                'status': 'FETCHED_UNVERIFIED', 'raw_file': 'ndr.html',
                'raw_sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw), 'http_status': 200, 'content_type': 'text/html'}],
        }
        (index / 'manifest.json').write_bytes(encode(manifest))
        if not missing:
            (index / 'ndr.html').write_bytes(raw)
        if rejected:
            (index / 'ndr.html').write_bytes(b'corrupt')
        def fetch(url):
            fixture = url.rsplit('-', 1)[1].removesuffix('.html')
            body = bodies.get(fixture, detail()) if bodies is not None else detail()
            if isinstance(body, Exception):
                raise body
            return body, 200, 'text/html', url
        with patch('ops.ndr_completion_collector.fetch_detail', side_effect=fetch):
            collect(index, completion, now=NOW)
        return index, completion

    def capture(self, root, **kwargs):
        index, completion = self.make(root, **kwargs)
        target = root / 'ndr-capture.tar'
        summary = prepare(index, completion, target, now=NOW)
        return target.read_bytes(), summary

    def assert_rejected(self, raw):
        with self.assertRaises(ValueError):
            validate_capture(raw, now=NOW)

    def test_original_bytes_deterministic_safe_summary_and_no_source_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = self.make(root)
            before = {str(path): path.read_bytes() for folder in [index, completion] for path in folder.iterdir()}
            first, second = root / 'first', root / 'second'
            first.mkdir()
            second.mkdir()
            a, b = first / 'ndr-capture.tar', second / 'ndr-capture.tar'
            summary = prepare(index, completion, a, now=NOW)
            prepare(index, completion, b, now=NOW)
            self.assertEqual(a.read_bytes(), b.read_bytes())
            self.assertEqual(before, {str(path): path.read_bytes() for folder in [index, completion] for path in folder.iterdir()})
            files = unpack(a.read_bytes())
            self.assertEqual(files['index-manifest.json'], (index / 'manifest.json').read_bytes())
            self.assertEqual(files['completion-manifest.json'], (completion / 'manifest.json').read_bytes())
            self.assertEqual(files['report.json'], (completion / 'report.json').read_bytes())
            self.assertEqual(summary['observation_count'], 1)
            self.assertTrue(summary['controlled_capture_content_verified'])
            for field in ['independently_verified', 'eligible_for_model_scoring', 'formal_eligible']:
                self.assertIs(summary[field], False)
            for field in ['observations', 'score_ft', 'ft', 'y', 'raw_html', 'completion_authenticated']:
                self.assertNotIn(field, summary)
            self.assertEqual(validate_capture(a.read_bytes(), witness=NOW, now=NOW), summary)
            with tarfile.open(a) as archive:
                for member in archive.getmembers():
                    self.assertTrue(member.isreg())
                    self.assertEqual((member.uid, member.gid, member.mtime, member.mode, member.uname, member.gname), (0, 0, 0, 0o600, '', ''))

    def test_reconstructs_observations_and_exact_manifest_report_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp))
            for attack in ['observation', 'count', 'unsafe', 'bool_count', 'manifest', 'source_index', 'limit', 'extra']:
                with self.subTest(attack=attack):
                    files = unpack(raw)
                    report = json.loads(files['report.json'])
                    if attack == 'observation':
                        report['observations'][0]['display_score']['home'] = 2
                    elif attack == 'count':
                        report['observation_count'] = 0
                    elif attack == 'unsafe':
                        report['observations'][0]['independently_verified'] = True
                    elif attack == 'bool_count':
                        report['requests_attempted'] = True
                    elif attack == 'manifest':
                        manifest = json.loads(files['completion-manifest.json'])
                        manifest['sources'][0]['bytes'] += 1
                        files['completion-manifest.json'] = encode(manifest)
                    elif attack == 'source_index':
                        report['source_index']['raw_sha256'] = '0' * 64
                    elif attack == 'limit':
                        report['max_requests'] = 1
                    else:
                        report['invented'] = True
                    files['report.json'] = encode(report)
                    self.assert_rejected(repack(files))

    def test_raw_mutation_and_forged_hash_still_need_reparse(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp))
            for rehash in [False, True]:
                files = unpack(raw)
                files['ndr-detail-5884.html'] = detail().replace(b'finalresult">1:0', b'finalresult">2:0')
                if rehash:
                    report = json.loads(files['report.json'])
                    source = report['sources'][0]
                    source['raw_sha256'] = hashlib.sha256(files[source['raw_file']]).hexdigest()
                    report['observations'][0]['detail_source'] = copy.deepcopy(source)
                    manifest = json.loads(files['completion-manifest.json'])
                    manifest['sources'] = copy.deepcopy(report['sources'])
                    files['report.json'], files['completion-manifest.json'] = encode(report), encode(manifest)
                self.assert_rejected(repack(files))

    def test_failures_and_source_unavailable_are_replayed_without_observations(self):
        cases = [dict(missing=True), dict(rows=row(score='LIVE')),
                 dict(bodies={'5884': URLError('untrusted details')}),
                 dict(bodies={'5884': HTTPError('url', 503, 'hidden', {}, None)}),
                 dict(bodies={'5884': detail().replace(b'>Ende<', b'>Live<')})]
        for options in cases:
            with self.subTest(options=str(options)[:60]), tempfile.TemporaryDirectory() as tmp:
                raw, summary = self.capture(Path(tmp), **options)
                self.assertEqual(summary['observation_count'], 0)
                self.assertEqual(validate_capture(raw, now=NOW), summary)
                files = unpack(raw)
                report = json.loads(files['report.json'])
                if report['fetch_errors']:
                    report['fetch_errors'][0]['reason'] = 'FORGED_REASON'
                elif report['rejections']:
                    report['rejections'][0]['reason'] = 'FORGED_REASON'
                else:
                    report['attempt_count'] = 1
                files['report.json'] = encode(report)
                self.assert_rejected(repack(files))

    def test_first_three_index_rows_only_and_no_unlisted_raw(self):
        rows = ''.join(row(fixture=str(5884+i), home=str(264+i), date=f'{16+i:02d}.10.') for i in range(5))
        with tempfile.TemporaryDirectory() as tmp:
            raw, summary = self.capture(Path(tmp), rows=rows)
            self.assertEqual(summary['requests_attempted'], 3)
            files = unpack(raw)
            report = json.loads(files['report.json'])
            self.assertEqual([source['provider_fixture_id'] for source in report['sources']], ['5884', '5885', '5886'])
            report['sources'].reverse()
            files['report.json'] = encode(report)
            self.assert_rejected(repack(files))
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp), missing=True)
            files = unpack(raw)
            files['ndr.html'] = page()
            self.assert_rejected(repack(files))

    def test_chronology_and_witness_bounds_cover_every_recorded_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp))
            self.assertEqual(validate_capture(raw, witness=NOW.isoformat(), now=NOW)['requests_attempted'], 1)
            self.assertEqual(validate_capture(raw, witness=NOW+timedelta(minutes=5), now=NOW)['requests_attempted'], 1)
            with self.assertRaises(ValueError):
                validate_capture(raw, witness=NOW-timedelta(seconds=1), now=NOW)
            with self.assertRaises(ValueError):
                validate_capture(raw, witness=NOW+timedelta(minutes=5, seconds=1), now=NOW)
            for field, value in [('requested_utc', NOW-timedelta(minutes=1)), ('captured_utc', NOW+timedelta(seconds=1))]:
                files = unpack(raw)
                report = json.loads(files['report.json'])
                report['sources'][0][field] = value.isoformat()
                report['observations'][0]['detail_source'][field] = value.isoformat()
                manifest = json.loads(files['completion-manifest.json'])
                manifest['sources'] = copy.deepcopy(report['sources'])
                files['report.json'], files['completion-manifest.json'] = encode(report), encode(manifest)
                self.assert_rejected(repack(files))

    def test_error_sources_own_no_raw_bytes_or_success_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp), bodies={'5884': URLError('hidden')})
            for field, value in [('captured_utc', NOW.isoformat()), ('raw_file', 'ndr-detail-5884.html'),
                                 ('final_url', 'https://www.ndr.de/sport/ergebnisse/spielstatistik-5884.html'),
                                 ('error', 'UNRECOGNIZED_REASON')]:
                files = unpack(raw)
                report = json.loads(files['report.json'])
                report['sources'][0][field] = value
                manifest = json.loads(files['completion-manifest.json'])
                manifest['sources'] = copy.deepcopy(report['sources'])
                files['report.json'], files['completion-manifest.json'] = encode(report), encode(manifest)
                self.assert_rejected(repack(files))
            files = unpack(raw)
            files['ndr-detail-5884.html'] = detail()
            self.assert_rejected(repack(files))

    def test_unavailable_index_error_is_coherent_and_has_no_stale_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = self.make(root, missing=True)
            manifest = json.loads((index/'manifest.json').read_bytes())
            manifest['sources'] = [{'provider': 'NDR', 'source_url': SOURCE_URL, 'status': 'ERROR', 'error_type': 'TimeoutError'}]
            (index/'manifest.json').write_bytes(encode(manifest))
            target = root/'ndr-capture.tar'
            summary = prepare(index, completion, target, now=NOW)
            self.assertFalse(summary['source_available'])
            files = unpack(target.read_bytes())
            manifest['sources'][0]['raw_file'] = 'ndr.html'
            files['index-manifest.json'] = encode(manifest)
            self.assert_rejected(repack(files))

    def test_reduced_attempts_duplicate_identity_and_false_flags_are_rejected(self):
        rows = row() + row(fixture='999', home='999')
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp), rows=rows)
            files = unpack(raw)
            report = json.loads(files['report.json'])
            report['sources'] = report['sources'][:1]
            report['requests_attempted'] = report['attempt_count'] = 1
            report['rejections'] = []
            manifest = json.loads(files['completion-manifest.json'])
            manifest['requests_attempted'], manifest['sources'] = 1, copy.deepcopy(report['sources'])
            files['report.json'], files['completion-manifest.json'] = encode(report), encode(manifest)
            del files['ndr-detail-999.html']
            self.assert_rejected(repack(files))
            files = unpack(raw)
            files['ndr.html'] = page(row() + row())
            manifest = json.loads(files['index-manifest.json'])
            manifest['sources'][0].update(raw_sha256=hashlib.sha256(files['ndr.html']).hexdigest(), bytes=len(files['ndr.html']))
            files['index-manifest.json'] = encode(manifest)
            self.assert_rejected(repack(files))
            files = unpack(raw)
            report = json.loads(files['report.json'])
            report['sources'][0]['capture_time_independently_authenticated'] = True
            files['report.json'] = encode(report)
            self.assert_rejected(repack(files))

    def test_tar_rejects_links_duplicates_paths_extras_and_noncanonical_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp))
            files = unpack(raw)
            for name, kind in [('ndr.html', tarfile.REGTYPE), ('../ndr.html', tarfile.REGTYPE), ('bad', tarfile.DIRTYPE), ('link', tarfile.SYMTYPE), ('hard', tarfile.LNKTYPE), ('ndr-detail-000.html', tarfile.REGTYPE)]:
                with self.subTest(name=name, kind=kind):
                    info = tarfile.TarInfo(name)
                    info.type, info.mode = kind, 0o600
                    info.linkname = 'ndr.html' if kind in [tarfile.SYMTYPE, tarfile.LNKTYPE] else ''
                    self.assert_rejected(repack(files, info))
            self.assert_rejected(raw + b'unlisted trailing bytes')
            self.assert_rejected(b'not a tar')
            self.assert_rejected(b'0' * 16_000_001)
            files['ndr-detail-5884.html'] = b'a' * 3_000_001
            self.assert_rejected(repack(files))

    def test_duplicate_json_keys_and_nonfinite_values_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp))
            for name in ['index-manifest.json', 'completion-manifest.json', 'report.json']:
                for suffix in [b', "status":"HOLD"}', b', "untrusted":NaN}', b', "untrusted":1e999}']:
                    files = unpack(raw)
                    files[name] = files[name].rstrip()[:-1] + suffix
                    self.assert_rejected(repack(files))

    def test_index_manifest_cannot_embed_extra_claims_or_non_html_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = self.capture(Path(tmp))
            for scope, key, value in [('root', 'formal_eligible', True),
                                      ('root', 'source_identity_independently_authenticated', True),
                                      ('source', 'independently_verified', True),
                                      ('source', 'content_type', 'text/plain')]:
                files = unpack(raw)
                manifest = json.loads(files['index-manifest.json'])
                target = manifest if scope == 'root' else manifest['sources'][0]
                target[key] = value
                files['index-manifest.json'] = encode(manifest)
                self.assert_rejected(repack(files))

    def test_prepare_preflights_excess_detail_files_before_reading_any(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = self.make(root)
            for fixture in range(100, 104):
                (completion/f'ndr-detail-{fixture}.html').write_bytes(b'raw')
            with patch('ops.ndr_capture_pack._read', side_effect=AssertionError('must preflight before reads')):
                with self.assertRaises(ValueError):
                    prepare(index, completion, root/'ndr-capture.tar', now=NOW)

    def test_prepare_invalid_input_creates_no_output_and_refuses_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = self.make(root, rejected=True)
            target = root / 'ndr-capture.tar'
            with self.assertRaises(ValueError):
                prepare(index, completion, target, now=NOW)
            self.assertFalse(target.exists())
        for attack in ['inside', 'existing', 'symlink_input', 'hardlink_input', 'symlink_output']:
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                index, completion = self.make(root)
                target = index / 'ndr-capture.tar' if attack == 'inside' else root / 'ndr-capture.tar'
                if attack == 'existing':
                    target.write_bytes(b'KEEP')
                elif attack == 'symlink_input':
                    (index / 'ndr.html').unlink()
                    (index / 'ndr.html').symlink_to(completion / 'report.json')
                elif attack == 'hardlink_input':
                    os.link(index / 'ndr.html', root / 'alias')
                elif attack == 'symlink_output':
                    target.symlink_to(root / 'missing')
                with self.assertRaises((OSError, ValueError)):
                    prepare(index, completion, target, now=NOW)
                if attack == 'existing':
                    self.assertEqual(target.read_bytes(), b'KEEP')

    def test_cli_only_prints_safe_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index, completion = self.make(root)
            result = subprocess.run([sys.executable, '-m', 'ops.ndr_capture_pack', '--index', str(index), '--completion', str(completion), '--output', str(root/'ndr-capture.tar')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['observation_count'], 1)
            self.assertNotIn('Home', result.stdout)


if __name__ == '__main__':
    unittest.main()
