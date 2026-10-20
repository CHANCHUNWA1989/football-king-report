"""Original OpenLiga bytes are replayable, never authenticated football results."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from ops.openliga_capture_pack import prepare, validate_capture

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
WITNESS = NOW - timedelta(minutes=1)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def fixture(folder, *, other_error=False):
    folder.mkdir()
    raw = b'[ {"matchID":123,"matchIsFinished":true,"matchResults":[{"pointsTeam1":2,"pointsTeam2":1}]} ]\n'
    other = b'{"matches": []}\n'
    manifest = {'schema': 'football-king-raw-ft-source-candidates-v2',
                'captured_utc': '2026-10-20T11:00:00Z', 'season_start': 2026,
                'status': 'HOLD', 'independently_verified': False,
                'eligible_for_model_scoring': False, 'production_recommendations': 'DISABLED',
                'sources': []}
    for index, (provider, url, body) in enumerate([
            ('OpenLigaDB', 'https://api.openligadb.de/getmatchdata/bl1/2026', raw),
            ('OpenFootball', 'https://raw.githubusercontent.com/openfootball/football.json/master/2026-27/de.1.json', other)]):
        item = {'provider': provider, 'source_url': url,
                'status': 'FETCHED_UNVERIFIED', 'redirect_policy': 'DENY_ALL',
                'requested_utc': f'2026-10-20T11:0{index * 2}:00Z',
                'completed_utc': f'2026-10-20T11:0{index * 2 + 1}:00Z',
                'final_url': url, 'raw_file': provider.lower() + '.json',
                'raw_sha256': hashlib.sha256(body).hexdigest(), 'bytes': len(body),
                'http_status': 200, 'content_type': 'application/json'}
        if index == 1 and other_error:
            item = {k: v for k, v in item.items() if k not in
                    ('raw_file', 'raw_sha256', 'bytes', 'content_type')}
            item.update(status='ERROR', final_url=None, http_status=None,
                        error_type='TimeoutError', error_code='SOURCE_TIMEOUT')
        else:
            (folder / item['raw_file']).write_bytes(body)
        manifest['sources'].append(item)
    (folder / 'manifest.json').write_bytes(encode(manifest))
    return manifest


def unpack(raw):
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as stream:
        return {item.name: stream.extractfile(item).read() for item in stream.getmembers()}


def repack(files, *, extra=None, order=None, format=tarfile.USTAR_FORMAT):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=format) as archive:
        for name in order or files:
            item = tarfile.TarInfo(name)
            item.mode, item.size = 0o600, len(files[name])
            archive.addfile(item, io.BytesIO(files[name]))
        if extra is not None:
            archive.addfile(extra, io.BytesIO(b''))
    return stream.getvalue()


class OpenLigaCapturePackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.rawdir = self.root / 'raw'
        self.manifest = fixture(self.rawdir)
        self.target = self.root / 'proof' / 'openliga-capture.tar'

    def make(self):
        summary = prepare(self.rawdir, self.target, now=NOW)
        return self.target.read_bytes(), summary

    def reject(self, raw):
        with self.assertRaises(ValueError):
            validate_capture(raw, witness=WITNESS, now=NOW)

    def test_exact_original_bytes_single_source_scope_notice_and_determinism(self):
        before = {p.name: p.read_bytes() for p in self.rawdir.iterdir()}
        raw, summary = self.make()
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.rawdir.iterdir()})
        files = unpack(raw)
        self.assertEqual(set(files), {'manifest.json', 'openligadb.json', 'capture.json', 'NOTICE.txt'})
        for name in ('manifest.json', 'openligadb.json'):
            self.assertEqual(files[name], before[name])
        self.assertEqual(summary['origin_chain_scope'], 'OPENLIGADB_ONLY')
        self.assertEqual(summary['raw_record_count'], 1)
        self.assertEqual(summary['source_receipt'], self.manifest['sources'][0])
        self.assertEqual(summary['manifest_sha256'], hashlib.sha256(before['manifest.json']).hexdigest())
        for key in ('raw_source_identity_authenticated', 'actual_kickoff_authenticated',
                    'regulation_ft_authenticated', 'independently_verified',
                    'eligible_for_model_scoring', 'eligible_for_betting_promotion'):
            self.assertIs(summary[key], False)
        self.assertNotIn('matchID', files['capture.json'].decode())
        self.assertNotIn('pointsTeam', files['capture.json'].decode())
        notice = files['NOTICE.txt'].decode()
        for text in ('https://api.openligadb.de/getmatchdata/bl1/2026',
                     'OpenLigaDB/community contributors', 'Open Database License (ODbL) 1.0',
                     'https://opendatacommons.org/licenses/odbl/1-0/', 'unmodified', 'code license', 'Contains information from OpenLigaDB (https://www.openligadb.de/)'):
            self.assertIn(text, notice)
        other = self.root / 'other' / 'openliga-capture.tar'
        prepare(self.rawdir, other, now=NOW)
        self.assertEqual(raw, other.read_bytes())
        self.assertEqual(validate_capture(raw, witness=WITNESS, now=NOW), summary)

    def test_manifest_v1_missing_origin_and_openliga_failure_never_create_subject(self):
        for attack in ('legacy', 'missing_receipt', 'source_failure', 'wrong_url', 'redirect', 'status'):
            with self.subTest(attack=attack):
                manifest = copy.deepcopy(self.manifest)
                if attack == 'legacy':
                    manifest['schema'] = 'football-king-raw-ft-source-candidates-v1'
                elif attack == 'missing_receipt':
                    manifest['sources'][0].pop('completed_utc')
                elif attack == 'source_failure':
                    source = manifest['sources'][0]
                    for key in ('raw_file', 'raw_sha256', 'bytes', 'content_type'):
                        source.pop(key)
                    source.update(status='ERROR', final_url=None, http_status=None,
                                  error_type='TimeoutError', error_code='SOURCE_TIMEOUT')
                elif attack == 'wrong_url':
                    manifest['sources'][0]['source_url'] += '/evil'
                elif attack == 'redirect':
                    manifest['sources'][0]['redirect_policy'] = 'ALLOW'
                else:
                    manifest['sources'][0]['http_status'] = True
                (self.rawdir / 'manifest.json').write_bytes(encode(manifest))
                with self.assertRaises(ValueError) as failure:
                    prepare(self.rawdir, self.target, now=NOW)
                if attack == 'legacy':
                    self.assertIn('NOT_CONTROLLED_ORIGIN_CHAIN', str(failure.exception))
                self.assertFalse(self.target.exists())

    def test_openfootball_error_receipt_replayed_without_raw_or_authentication(self):
        folder = self.root / 'error-raw'
        fixture(folder, other_error=True)
        summary = prepare(folder, self.target, now=NOW)
        self.assertEqual(summary['origin_chain_scope'], 'OPENLIGADB_ONLY')
        self.assertIs(summary['raw_source_identity_authenticated'], False)
        self.assertNotIn('openfootball.json', unpack(self.target.read_bytes()))

    def test_tampered_original_bytes_raw_hash_summary_and_notice_fail_replay(self):
        raw, _ = self.make()
        for attack in ('raw', 'manifest', 'summary_count', 'bool_count', 'summary_receipt', 'unsafe_flag', 'notice'):
            with self.subTest(attack=attack):
                files = unpack(raw)
                if attack == 'raw':
                    files['openligadb.json'] += b' '
                elif attack == 'manifest':
                    files['manifest.json'] += b' '
                elif attack == 'notice':
                    files['NOTICE.txt'] += b' different'
                else:
                    summary = json.loads(files['capture.json'])
                    if attack == 'summary_count':
                        summary['raw_record_count'] = 7
                    elif attack == 'bool_count':
                        summary['raw_record_count'] = True
                    elif attack == 'summary_receipt':
                        summary['source_receipt']['raw_sha256'] = '0' * 64
                    else:
                        summary['regulation_ft_authenticated'] = True
                    files['capture.json'] = encode(summary)
                self.reject(repack(files))

    def test_tar_member_allowlist_duplicates_aliases_links_extensions_and_padding(self):
        raw, _ = self.make()
        files = unpack(raw)
        for name in ('../manifest.json', '/manifest.json', './manifest.json', 'openfootball.json', 'manifest.json'):
            with self.subTest(name=name):
                self.reject(repack(files, extra=tarfile.TarInfo(name)))
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE):
            member = tarfile.TarInfo('capture.json')
            member.type, member.linkname = kind, 'manifest.json'
            self.reject(repack(files, extra=member))
        self.reject(repack(files, order=list(reversed(files))))
        self.reject(raw + b'\0' * 10240)
        self.reject(raw[:-1] + b'x')
        self.reject(raw[:100])
        self.reject(repack(files, format=tarfile.PAX_FORMAT, extra=tarfile.TarInfo('x' * 200)))

    def test_raw_json_duplicate_nonfinite_schema_and_size_rejected_before_write(self):
        for body in (b'{}', b'[{"a":1,"a":2}]', b'[NaN]', b'[1e999]', b'\xff', b'x' * 3_000_001):
            with self.subTest(body=body[:25]):
                manifest = copy.deepcopy(self.manifest)
                manifest['sources'][0].update(bytes=len(body), raw_sha256=hashlib.sha256(body).hexdigest())
                (self.rawdir / 'manifest.json').write_bytes(encode(manifest))
                (self.rawdir / 'openligadb.json').write_bytes(body)
                with self.assertRaises(ValueError):
                    prepare(self.rawdir, self.target, now=NOW)
                self.assertFalse(self.target.exists())

    def test_all_receipt_times_must_precede_verified_rekor_without_future_grace(self):
        raw, _ = self.make()
        self.reject_clock(raw, datetime(2026, 10, 20, 11, 2, tzinfo=timezone.utc))
        self.reject_clock(raw, NOW + timedelta(microseconds=1))
        files = unpack(raw)
        manifest = json.loads(files['manifest.json'])
        manifest['sources'][1]['requested_utc'] = '2026-10-20T10:00:00Z'
        files['manifest.json'] = encode(manifest)
        self.reject(repack(files))

    def reject_clock(self, raw, witness):
        with self.assertRaises(ValueError):
            validate_capture(raw, witness=witness, now=NOW)

    def test_unsafe_paths_links_existing_output_and_read_mutation_fail(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.rawdir, target_is_directory=True)
        for folder, output in ((alias, self.target), (self.rawdir / '..' / 'raw', self.target),
                               (self.rawdir, self.rawdir / 'openliga-capture.tar')):
            with self.subTest(folder=folder, output=output), self.assertRaises(ValueError):
                prepare(folder, output, now=NOW)
        path = self.rawdir / 'openligadb.json'
        original = self.root / 'original.json'
        path.rename(original)
        for kind in ('symlink', 'hardlink'):
            path.symlink_to(original) if kind == 'symlink' else os.link(original, path)
            with self.assertRaises(ValueError):
                prepare(self.rawdir, self.target, now=NOW)
            path.unlink()
        original.rename(path)
        self.make()
        before = self.target.read_bytes()
        with self.assertRaises(ValueError):
            prepare(self.rawdir, self.target, now=NOW)
        self.assertEqual(self.target.read_bytes(), before)

    def test_input_reread_change_rejects_before_subject_creation(self):
        from ops.openliga_capture_pack import _read_regular
        calls = []
        def changed(path, maximum, identities=None):
            raw = _read_regular(path, maximum, identities)
            calls.append(path.name)
            return raw + b" " if len(calls) > 3 else raw
        with patch("ops.openliga_capture_pack._read_regular", side_effect=changed):
            with self.assertRaisesRegex(ValueError, 'INPUT_CHANGED_DURING_PREPARATION'):
                prepare(self.rawdir, self.target, now=NOW)
        self.assertFalse(self.target.exists())

    def test_output_write_failure_removes_only_own_new_subject(self):
        with patch('ops.openliga_capture_pack.os.fsync', side_effect=OSError('fixture disk error')):
            with self.assertRaises(OSError):
                prepare(self.rawdir, self.target, now=NOW)
        self.assertFalse(self.target.exists())
        self.assertTrue((self.rawdir / 'openligadb.json').is_file())

    def test_original_manifest_duplicate_keys_cannot_enter_subject(self):
        body = (self.rawdir / 'manifest.json').read_bytes()
        body = body.replace(b'"schema":', b'"schema":"fake","schema":', 1)
        (self.rawdir / 'manifest.json').write_bytes(body)
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_OPENLIGA_CAPTURE_JSON_KEY'):
            prepare(self.rawdir, self.target, now=NOW)
        self.assertFalse(self.target.exists())


if __name__ == '__main__':
    unittest.main()
