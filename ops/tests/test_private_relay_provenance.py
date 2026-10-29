"""Synthetic authenticated-response shapes, never live origin authentication."""
import copy
import hashlib
import importlib
import io
import json
import stat
import unittest
import zipfile


REPOSITORY = {'id': 1411226578, 'full_name': 'CHANCHUNWA1989/football-king-report'}
SOURCE = 'a' * 40
RECIPIENT = 'b' * 64
CONTEXT = {'source_sha': SOURCE, 'run_id': '101', 'attempt': '2'}
CIPHERTEXT = b'age-encryption.org/v1\nSYNTHETIC-CIPHERTEXT-NOT-REAL\n'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def zip_one(name, raw, *, method=zipfile.ZIP_DEFLATED, mode=stat.S_IFREG | 0o600):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        info = zipfile.ZipInfo(name)
        info.compress_type = method
        info.create_system = 3
        info.external_attr = mode << 16
        archive.writestr(info, raw)
    return stream.getvalue()


def receipt():
    return {'schema': 'football-king-private-response-relay-v1',
            'operation': 'encrypt', 'relay_status': 'ENCRYPTED', **CONTEXT,
            'manifest_sha256': 'c' * 64, 'archive_sha256': 'd' * 64,
            'ciphertext_sha256': sha(CIPHERTEXT), 'recipient_sha256': RECIPIENT,
            'archive_bytes': 20, 'ciphertext_bytes': len(CIPHERTEXT), 'capture_count': 1,
            'encryption': 'age-v1.3.2-native-pq', 'raw_source_authenticated': False,
            'capture_time_authenticated': False, 'durable_archive_verified': False,
            'production_recommendations': 'DISABLED', 'status': 'HOLD',
            'certified_case_count': 0, 'eligible_for_model_scoring': False,
            'eligible_for_betting_promotion': False}


def artifact(identifier, kind, raw):
    return {'id': identifier, 'name': 'football-private-original-' + kind + '-101-2',
            'size_in_bytes': len(raw), 'expired': False, 'digest': 'sha256:' + sha(raw),
            'workflow_run': {'id': 101, 'repository_id': REPOSITORY['id'],
                             'head_repository_id': REPOSITORY['id'],
                             'head_branch': 'main', 'head_sha': SOURCE}}


class PrivateRelayProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.run = {'id': 101, 'run_attempt': 2, 'head_sha': SOURCE,
                    'head_branch': 'main', 'event': 'schedule',
                    'path': '.github/workflows/private-all-market-research.yml',
                    'status': 'completed', 'conclusion': 'success',
                    'repository': dict(REPOSITORY), 'head_repository': dict(REPOSITORY)}
        self.receipt = receipt()
        self.rebuild()

    def module(self):
        return importlib.import_module('ops.private_relay_provenance')

    def expected(self, **changes):
        args = dict(**CONTEXT, workflow_path=self.run['path'], recipient_sha256=RECIPIENT)
        args.update(changes)
        return self.module().ExpectedRun(**args)

    def rebuild(self, *, cipher_zip=None, receipt_raw=None, receipt_zip=None):
        self.cipher_zip = cipher_zip if cipher_zip is not None else zip_one(
            'original-response-pack.zip.age', CIPHERTEXT)
        payload = receipt_raw if receipt_raw is not None else json.dumps(self.receipt).encode()
        self.receipt_zip = receipt_zip if receipt_zip is not None else zip_one('producer-receipt.json', payload)
        self.cipher_meta = artifact(501, 'ciphertext', self.cipher_zip)
        self.receipt_meta = artifact(502, 'receipt', self.receipt_zip)

    def verify(self, **changes):
        args = dict(run_metadata=self.run, cipher_artifact_metadata=self.cipher_meta,
                    cipher_artifact_zip=self.cipher_zip, receipt_artifact_metadata=self.receipt_meta,
                    receipt_artifact_zip=self.receipt_zip, expected=self.expected())
        args.update(changes)
        return self.module().verify_bundle(**args)

    def test_same_run_metadata_zip_and_external_recipient_bind_safe_receipt(self):
        result = self.verify()
        self.assertEqual(result.receipt, self.receipt)
        self.assertEqual(result.ciphertext, CIPHERTEXT)
        self.assertTrue(result.report['github_metadata_and_digest_bound'])
        self.assertTrue(result.report['authenticated_github_fetch_required'])
        self.assertFalse(result.report['raw_source_authenticated'])
        self.assertEqual(result.report['certified_case_count'], 0)
        self.assertEqual(result.report['production_recommendations'], 'DISABLED')

    def test_trusted_source_workflow_branch_event_run_and_attempt_all_required(self):
        mutations = [('source_sha', 'e' * 40), ('workflow_path', '.github/workflows/other.yml'),
                     ('head_branch', 'other'), ('run_id', '102'), ('attempt', '1'),
                     ('recipient_sha256', 'e' * 64), ('allowed_events', ('push',))]
        for key, value in mutations:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(expected=self.expected(**{key: value}))

    def test_wrong_repository_fork_unfinished_failure_and_pull_request_reject(self):
        for key, value in [('repository', {**REPOSITORY, 'id': 1}),
                           ('head_repository', {**REPOSITORY, 'full_name': 'Other/fork'}),
                           ('status', 'in_progress'), ('conclusion', 'failure'),
                           ('event', 'pull_request'), ('id', True), ('run_attempt', True)]:
            original = self.run
            self.run = {**original, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError): self.verify()
            self.run = original

    def test_artifact_identity_digest_size_expiry_and_cross_run_reject(self):
        for which in ('cipher_meta', 'receipt_meta'):
            original = getattr(self, which)
            mutations = [{'id': True}, {'expired': True}, {'size_in_bytes': True},
                         {'size_in_bytes': len(self.cipher_zip) + 1},
                         {'digest': 'sha256:' + '0' * 64}, {'name': 'football-private-original-ciphertext-101-1'},
                         {'workflow_run': {**original['workflow_run'], 'id': 102}},
                         {'workflow_run': {**original['workflow_run'], 'repository_id': 1}},
                         {'workflow_run': {**original['workflow_run'], 'head_repository_id': 1}},
                         {'workflow_run': {**original['workflow_run'], 'head_sha': 'e' * 40}},
                         {'workflow_run': {**original['workflow_run'], 'head_branch': 'fork'}}]
            for change in mutations:
                setattr(self, which, {**original, **change})
                with self.subTest(which=which, change=change), self.assertRaises(ValueError): self.verify()
            setattr(self, which, original)

    def test_artifact_zip_is_exact_one_allowed_regular_member(self):
        bad = [zip_one('../original-response-pack.zip.age', CIPHERTEXT),
               zip_one('original-response-pack.zip.age', CIPHERTEXT, mode=stat.S_IFLNK | 0o777),
               zip_one('original-response-pack.zip.age', CIPHERTEXT, method=zipfile.ZIP_BZIP2),
               zip_one('producer-receipt.json', CIPHERTEXT)]
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('original-response-pack.zip.age', CIPHERTEXT)
            archive.writestr('secret-key.txt', b'SYNTHETIC-KEY-MARKER')
        bad.append(stream.getvalue())
        for raw in bad:
            self.rebuild(cipher_zip=raw)
            with self.subTest(raw_bytes=len(raw)), self.assertRaises(ValueError): self.verify()

    def test_zip_prefix_trailer_corruption_and_same_artifact_id_reject(self):
        baseline = self.cipher_zip
        for raw in (b'RAW-PREFIX' + baseline, baseline + b'RAW-TRAILER',
                    baseline[:60] + b'\x00' * 20 + baseline[80:]):
            self.rebuild(cipher_zip=raw)
            with self.subTest(size=len(raw)), self.assertRaises(ValueError): self.verify()
        self.rebuild()
        self.receipt_meta['id'] = self.cipher_meta['id']
        with self.assertRaises(ValueError): self.verify()

    def test_receipt_exact_schema_no_duplicate_keys_or_authenticated_claims(self):
        baseline = receipt()
        for changes in ({'secret': 'MUST_NOT_SURVIVE'}, {'operation': 'decrypt'},
                        {'status': 'READY'}, {'raw_source_authenticated': True},
                        {'capture_time_authenticated': True}, {'durable_archive_verified': True},
                        {'production_recommendations': 'ENABLED'}, {'certified_case_count': True},
                        {'capture_count': True}, {'archive_bytes': True}, {'ciphertext_bytes': True},
                        {'ciphertext_sha256': '0' * 64}, {'ciphertext_bytes': len(CIPHERTEXT) + 1},
                        {'manifest_sha256': 'INVALID'}, {'recipient_sha256': '0' * 64},
                        {'run_id': '102'}, {'attempt': '1'}, {'source_sha': 'e' * 40}):
            self.receipt = {**baseline, **changes}; self.rebuild()
            with self.subTest(changes=changes), self.assertRaises(ValueError): self.verify()
        self.receipt = baseline
        duplicate = json.dumps(baseline)[:-1] + ',"run_id":"101"}'
        self.rebuild(receipt_raw=duplicate.encode())
        with self.assertRaises(ValueError): self.verify()
        self.rebuild(receipt_raw=b'{"invalid":NaN}')
        with self.assertRaises(ValueError): self.verify()

    def test_expected_constructor_rejects_ambiguous_identity_values(self):
        for change in ({'run_id': 101}, {'run_id': '0101'}, {'attempt': True},
                       {'repository_id': True}, {'repository_full_name': 'Owner/Other'},
                       {'source_sha': 'A' * 40}, {'recipient_sha256': 'bad'},
                       {'workflow_path': '../work.yml'}, {'allowed_events': ('pull_request',)},
                       {'head_branch': '../main'}):
            with self.subTest(change=change), self.assertRaises(ValueError): self.expected(**change)

    def test_explicit_reviewed_synthetic_branch_allowed_without_relaxing_main_default(self):
        self.run.update(head_branch='research/drive-relay-20261029', event='push')
        for item in (self.cipher_meta, self.receipt_meta):
            item['workflow_run']['head_branch'] = self.run['head_branch']
        result = self.verify(expected=self.expected(head_branch=self.run['head_branch'], allowed_events=('push',)))
        self.assertEqual(result.report['head_branch'], self.run['head_branch'])
        with self.assertRaises(ValueError): self.verify()


if __name__ == '__main__':
    unittest.main()
