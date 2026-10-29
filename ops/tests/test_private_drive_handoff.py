"""Local real-age synthetic prepare, without authenticated fetch or Drive."""
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout

from ops.private_response_capture import CaptureSession, replay_records
from ops.private_response_relay import encrypt
from ops.tests.test_private_relay_provenance import artifact, zip_one, REPOSITORY

AGE = Path(os.environ.get('FOOTBALL_AGE_BINARY', '/workspace/tools/age-v1.3.2/age'))
ROOT = Path(__file__).resolve().parents[2]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


@unittest.skipUnless(AGE.is_file(), 'official pinned age required for handoff integration')
class PrivateDriveHandoffTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module('ops.private_drive_handoff')
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.repo = self.base / 'repo'; self.repo.mkdir()
        self.identity = self.base / 'synthetic-key.txt'
        subprocess.run([str(AGE.with_name('age-keygen')), '-pq', '-o', str(self.identity)],
                       stdin=subprocess.DEVNULL, capture_output=True, check=True)
        self.recipient = subprocess.check_output([str(AGE.with_name('age-keygen')), '-y',
                                                  str(self.identity)]).decode().strip()
        workflow = '.github/workflows/private-original-relay-synthetic.yml'
        paths = [*self.module.REQUIRED_CODE_PATHS, workflow]
        for name in paths:
            p = self.repo / name; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((ROOT / name).read_bytes())
        (self.repo / self.module.RECIPIENT_PATH).write_text(self.recipient + '\n')
        self.git('init', '-q'); self.git('add', '.')
        self.git('-c', 'user.name=Synthetic Test', '-c', 'user.email=synthetic@example.invalid',
                 'commit', '-qm', 'Synthetic reviewed source fixture')
        source = self.git('rev-parse', 'HEAD').stdout.decode().strip()
        self.context = {'source_sha': source, 'run_id': '101', 'attempt': '2'}
        self.config = {'schema': self.module.CONFIG_SCHEMA, 'recipient_sha256': digest(self.recipient.encode()),
                       'trusted_code_sha256': {name: digest((self.repo / name).read_bytes()) for name in paths},
                       'workflows': {workflow: {'head_branch': 'main', 'allowed_events': ['push']}}}
        self.config_path = self.write('trusted-config.json', self.config)
        now = datetime(2026, 10, 29, tzinfo=timezone.utc)
        self.body = b'[{"SYNTHETIC_ONLY":true}]\n'; source_dir = self.base / 'source'
        with CaptureSession(source_dir, **self.context) as session:
            session.record(self.body, path='/sports/', quota={'used': 0, 'remaining': 0, 'last': 0},
                           requested=now, completed=now, secret='synthetic-guard')
            pin = session.seal()['manifest_sha256']
        cipher = self.base / 'cipher.age'
        self.producer = encrypt(source_dir, cipher, **self.context, expected_manifest_sha256=pin,
                                recipient=self.recipient, age_binary=AGE)
        self.run = {'id': 101, 'run_attempt': 2, 'head_sha': source, 'head_branch': 'main',
                    'path': workflow, 'event': 'push', 'status': 'completed', 'conclusion': 'success',
                    'repository': dict(REPOSITORY), 'head_repository': dict(REPOSITORY)}
        self.run_path = self.write('run.json', self.run)
        self.cipher_zip = self.write('cipher.zip', zip_one('original-response-pack.zip.age', cipher.read_bytes()))
        self.receipt_zip = self.write('receipt.zip', zip_one('producer-receipt.json', json.dumps(self.producer).encode()))
        self.meta_paths = []
        for identifier, kind, path in ((501, 'ciphertext', self.cipher_zip), (502, 'receipt', self.receipt_zip)):
            meta = artifact(identifier, kind, path.read_bytes())
            meta['workflow_run']['head_sha'] = source
            self.meta_paths.append(self.write(kind + '-metadata.json', meta))
        self.output = self.base / 'prepared'

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.repo), *args], capture_output=True, check=True)

    def write(self, name, value):
        p = self.base / name
        p.write_bytes(value if isinstance(value, bytes) else (json.dumps(value) + '\n').encode())
        p.chmod(0o600); return p

    def prepare(self, **changes):
        args = dict(run_metadata=self.run_path, cipher_metadata=self.meta_paths[0],
                    receipt_metadata=self.meta_paths[1], cipher_zip=self.cipher_zip,
                    receipt_zip=self.receipt_zip, trusted_config=self.config_path,
                    source_repository=self.repo, identity_file=self.identity, age_binary=AGE,
                    output_dir=self.output)
        args.update(changes); return self.module.prepare(**args)

    def test_real_age_synthetic_bundle_code_pins_and_canonical_original_prepare(self):
        result = self.prepare()
        packed = (self.output / 'original-response-pack.zip').read_bytes()
        self.assertEqual(digest(packed), self.producer['archive_sha256'])
        self.assertEqual(replay_records(self.output / 'restoredpack', **self.context,
                         expected_manifest_sha256=self.producer['manifest_sha256'])[0]['raw'], self.body)
        self.assertTrue(result['source_code_pins_verified']); self.assertTrue(result['local_code_pins_verified'])
        self.assertEqual(result['handoff_status'], 'PREPARED_NOT_STORED')
        self.assertFalse(result['durable_archive_verified']); self.assertEqual(result['status'], 'HOLD')
        self.assertEqual(result['production_recommendations'], 'DISABLED')
        self.assertNotIn(str(self.base), json.dumps(result)); self.assertNotIn('AGE-SECRET', json.dumps(result))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.output / 'original-response-pack.zip').stat().st_mode & 0o777, 0o600)
        self.assertTrue((self.output / 'safehandoff-receipt.json').exists())

    def test_wrong_code_pin_or_unreviewed_source_changes_reject_before_output(self):
        self.config['trusted_code_sha256']['ops/private_response_capture.py'] = '0' * 64
        self.write(self.config_path.name, self.config)
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())

    def test_wrong_run_context_or_cipher_bytes_reject_before_output(self):
        self.run['head_sha'] = 'a' * 40; self.write(self.run_path.name, self.run)
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())

    def test_unknown_config_path_and_nonprivate_config_reject(self):
        self.config['trusted_code_sha256']['private/secret.txt'] = '0' * 64
        self.write(self.config_path.name, self.config)
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())
        del self.config['trusted_code_sha256']['private/secret.txt']
        self.write(self.config_path.name, self.config); self.config_path.chmod(0o644)
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())

    def test_existing_or_repository_output_never_overwritten(self):
        self.output.mkdir(mode=0o700); (self.output / 'keep').write_bytes(b'unchanged')
        with self.assertRaises(ValueError): self.prepare()
        self.assertEqual((self.output / 'keep').read_bytes(), b'unchanged')
        with self.assertRaises(ValueError): self.prepare(output_dir=self.repo / 'raw-output')
        self.assertFalse((self.repo / 'raw-output').exists())

    def test_cli_errors_are_fixed_and_never_echo_private_paths(self):
        out = io.StringIO()
        with redirect_stdout(out): status = self.module.main(['prepare', '--trusted-config', str(self.config_path)])
        self.assertEqual(status, 1)
        report = json.loads(out.getvalue())
        self.assertEqual(report['status'], 'HOLD'); self.assertNotIn(str(self.base), out.getvalue())


if __name__ == '__main__': unittest.main()
