"""Standard age with synthetic originals only; no network or real keys."""
from datetime import datetime, timezone
from contextlib import redirect_stdout
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ops.private_response_capture import CaptureSession, replay_records

AGE = Path(os.environ.get('FOOTBALL_AGE_BINARY', '/workspace/tools/age-v1.3.2/age'))
CONTEXT = {'source_sha': 'a' * 40, 'run_id': '101', 'attempt': '1'}


@unittest.skipUnless(AGE.is_file(), 'official pinned age required for crypto integration')
class PrivateResponseRelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.raw = b'[{"synthetic_only":true,"real_football_data":false}]\n'
        now = datetime(2026, 10, 29, tzinfo=timezone.utc)
        self.source = self.root / 'source'
        with CaptureSession(self.source, **CONTEXT) as session:
            session.record(self.raw, path='/sports/', quota={'used': 0, 'remaining': 0, 'last': 0},
                           requested=now, completed=now, secret='synthetic-provider-guard')
            self.pin = session.seal()['manifest_sha256']
        self.identity = self.root / 'synthetic-key.txt'
        result = subprocess.run([str(AGE.with_name('age-keygen')), '-pq', '-o', str(self.identity)],
                                stdin=subprocess.DEVNULL, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.recipient = subprocess.check_output([str(AGE.with_name('age-keygen')), '-y',
                                                  str(self.identity)]).decode().strip()
        self.cipher = self.root / 'original-response-pack.zip.age'

    def module(self):
        return importlib.import_module('ops.private_response_relay')

    def encrypt(self, **changes):
        args = dict(CONTEXT, expected_manifest_sha256=self.pin, recipient=self.recipient, age_binary=AGE)
        args.update(changes)
        return self.module().encrypt(self.source, self.cipher, **args)

    def decrypt(self, receipt=None, destination=None, **changes):
        receipt = receipt or self.encrypt()
        args = dict(CONTEXT, expected_manifest_sha256=self.pin,
                    expected_archive_sha256=receipt['archive_sha256'],
                    expected_ciphertext_sha256=receipt['ciphertext_sha256'],
                    expected_recipient_sha256=receipt['recipient_sha256'],
                    identity_path=self.identity, age_binary=AGE)
        args.update(changes)
        return self.module().decrypt(self.cipher, destination or self.root / 'restored', **args)

    def test_real_age_roundtrip_replays_exact_original_and_false_flags(self):
        receipt = self.encrypt()
        restored = self.decrypt(receipt)
        self.assertEqual(receipt['recipient_sha256'], hashlib.sha256(self.recipient.encode()).hexdigest())
        self.assertEqual(receipt['ciphertext_sha256'], hashlib.sha256(self.cipher.read_bytes()).hexdigest())
        self.assertEqual(receipt['operation'], 'encrypt')
        self.assertEqual(receipt['relay_status'], 'ENCRYPTED')
        self.assertEqual(restored['capture_count'], 1)
        self.assertEqual(replay_records(self.root / 'restored', **CONTEXT,
                                       expected_manifest_sha256=self.pin)[0]['raw'], self.raw)
        for report in (receipt, restored):
            self.assertFalse(report['raw_source_authenticated'])
            self.assertFalse(report['capture_time_authenticated'])
            self.assertFalse(report['durable_archive_verified'])
            self.assertEqual(report['certified_case_count'], 0)
            self.assertEqual(report['status'], 'HOLD')
            self.assertEqual(report['production_recommendations'], 'DISABLED')
            self.assertNotIn('AGE-SECRET-KEY', json.dumps(report))
            self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(self.cipher.stat().st_mode & 0o777, 0o600)

    def test_wrong_key_tamper_and_truncation_never_install_plaintext(self):
        receipt = self.encrypt()
        wrong_key = self.root / 'wrong-synthetic-key.txt'
        subprocess.run([str(AGE.with_name('age-keygen')), '-pq', '-o', str(wrong_key)],
                       stdin=subprocess.DEVNULL, capture_output=True, check=True)
        with self.assertRaisesRegex(ValueError, '^PRIVATE_RELAY_CRYPTO_REJECTED$'):
            self.decrypt(receipt, identity_path=wrong_key)
        self.assertFalse((self.root / 'restored').exists())
        original = self.cipher.read_bytes()
        for malformed in (original[:-1], original[:-1] + bytes([original[-1] ^ 1])):
            self.cipher.write_bytes(malformed)
            with self.assertRaisesRegex(ValueError, '^PRIVATE_RELAY_CRYPTO_REJECTED$'):
                self.decrypt(receipt, expected_ciphertext_sha256=hashlib.sha256(malformed).hexdigest())
            self.assertFalse((self.root / 'restored').exists())

    def test_external_pins_and_context_cannot_be_replaced_by_payload_claims(self):
        receipt = self.encrypt()
        for changes, expected in (
            ({'expected_ciphertext_sha256': '0' * 64}, 'PRIVATE_RELAY_CIPHERTEXT_PIN_MISMATCH'),
            ({'expected_archive_sha256': '0' * 64}, 'PRIVATE_RELAY_ARCHIVE_PIN_MISMATCH'),
            ({'expected_manifest_sha256': '0' * 64}, 'PRIVATE_RELAY_OPERATION_REJECTED'),
            ({'run_id': '102'}, 'PRIVATE_RELAY_OPERATION_REJECTED'),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, '^' + expected + '$'):
                self.decrypt(receipt, **changes)
            self.assertFalse((self.root / 'restored').exists())

    def test_existing_ciphertext_and_restore_destination_never_overwritten(self):
        receipt = self.encrypt()
        before = self.cipher.read_bytes()
        with self.assertRaises(ValueError):
            self.encrypt()
        self.assertEqual(self.cipher.read_bytes(), before)
        destination = self.root / 'existing'
        destination.mkdir(mode=0o700)
        (destination / 'keep').write_bytes(b'unchanged')
        with self.assertRaises(ValueError):
            self.decrypt(receipt, destination=destination)
        self.assertEqual((destination / 'keep').read_bytes(), b'unchanged')

    def test_symlink_public_recipient_private_key_cipher_and_repo_paths_rejected(self):
        receipt = self.encrypt()
        link = self.root / 'link-key'
        link.symlink_to(self.identity)
        with self.assertRaises(ValueError):
            self.decrypt(receipt, identity_path=link)
        self.identity.chmod(0o644)
        with self.assertRaises(ValueError):
            self.decrypt(receipt)
        self.identity.chmod(0o600)
        original = self.root / 'original.age'
        self.cipher.rename(original)
        self.cipher.symlink_to(original)
        with self.assertRaises(ValueError):
            self.decrypt(receipt)
        self.cipher.unlink()
        original.rename(self.cipher)
        repository = self.root / 'repository'
        repository.mkdir(mode=0o700)
        (repository / '.git').mkdir()
        with self.assertRaises(ValueError):
            self.module().encrypt(self.source, repository / 'cipher.age', **CONTEXT,
                expected_manifest_sha256=self.pin, recipient=self.recipient, age_binary=AGE)

    def test_secret_identity_plugins_unpinned_binary_and_invalid_pins_rejected(self):
        secret_line = next(line for line in self.identity.read_text().splitlines()
                           if line.startswith('AGE-SECRET-KEY'))
        for recipient in (secret_line, 'age1plugin1invalid', self.recipient + '\n' + self.recipient):
            with self.assertRaises(ValueError):
                self.encrypt(recipient=recipient)
        fake = self.root / 'fake-age'
        fake.write_bytes(b'#!/bin/sh\nprintf should-not-run\n')
        fake.chmod(0o700)
        with self.assertRaisesRegex(ValueError, '^PRIVATE_RELAY_TOOL_PIN_MISMATCH$'):
            self.encrypt(age_binary=fake)
        with self.assertRaises(ValueError):
            self.encrypt(expected_manifest_sha256=True)
        self.assertFalse(self.cipher.exists())

    def test_ciphertext_size_cap_rejects_before_crypto(self):
        receipt = self.encrypt()
        with self.cipher.open('r+b') as stream:
            stream.truncate(self.module().MAX_CIPHERTEXT_BYTES + 1)
        with self.assertRaises(ValueError):
            self.decrypt(receipt)
        self.assertFalse((self.root / 'restored').exists())

    def test_cli_public_recipient_from_checkout_and_separate_safe_receipt(self):
        checkout = self.root / 'checkout'
        checkout.mkdir(mode=0o700)
        (checkout / '.git').mkdir()
        recipient = checkout / 'recipient.txt'
        recipient.write_text(self.recipient + '\n')
        recipient.chmod(0o644)
        output = self.root / 'producer-receipt.json'
        arguments = ['encrypt', '--private-dir', str(self.source), '--ciphertext', str(self.cipher),
                     '--source-sha', CONTEXT['source_sha'], '--run-id', CONTEXT['run_id'],
                     '--attempt', CONTEXT['attempt'], '--expected-manifest-sha256', self.pin,
                     '--recipient-file', str(recipient), '--age-binary', str(AGE),
                     '--receipt-output', str(output)]
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(self.module().main(arguments), 0)
        receipt = json.loads(output.read_bytes())
        self.assertEqual(json.loads(stdout.getvalue()), receipt)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn('AGE-SECRET-KEY', stdout.getvalue())
        self.assertNotIn(str(self.root), stdout.getvalue())
        output.unlink();self.cipher.unlink()
        recipient.unlink();recipient.symlink_to(self.identity)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(self.module().main(arguments), 1)
        self.assertFalse(self.cipher.exists())
        self.assertFalse(output.exists())
        self.assertNotIn('AGE-SECRET-KEY', stdout.getvalue())

    def test_large_late_tamper_removes_quarantine_before_any_install(self):
        source = self.root / 'large-source'
        now = datetime(2026, 10, 29, tzinfo=timezone.utc)
        body = b'[{"synthetic_only":true,"padding":"' + b'x' * 200_000 + b'"}]\n'
        with CaptureSession(source, **CONTEXT) as session:
            session.record(body, path='/sports/', quota={'used': 0, 'remaining': 0, 'last': 0},
                           requested=now, completed=now, secret='synthetic-provider-guard')
            pin = session.seal()['manifest_sha256']
        receipt = self.module().encrypt(source, self.cipher, **CONTEXT,
            expected_manifest_sha256=pin, recipient=self.recipient, age_binary=AGE)
        original = self.cipher.read_bytes()
        malformed = original[:-1] + bytes([original[-1] ^ 1])
        self.cipher.write_bytes(malformed)
        factory = tempfile.TemporaryDirectory
        directories = []
        def tracked(*args, **kwargs):
            temporary = factory(*args, **kwargs)
            directories.append(Path(temporary.name))
            return temporary
        with patch('ops.private_response_relay.tempfile.TemporaryDirectory', side_effect=tracked):
            with self.assertRaisesRegex(ValueError, '^PRIVATE_RELAY_CRYPTO_REJECTED$'):
                self.decrypt(receipt, expected_manifest_sha256=pin,
                    expected_ciphertext_sha256=hashlib.sha256(malformed).hexdigest())
        self.assertTrue(directories)
        self.assertTrue(all(not directory.exists() for directory in directories))
        self.assertFalse((self.root / 'restored').exists())

    def test_identity_plugin_and_malformed_public_pins_fail_closed(self):
        receipt = self.encrypt()
        self.identity.write_bytes(b'AGE-PLUGIN-ATTACKER-1TEST\n')
        with self.assertRaisesRegex(ValueError, '^PRIVATE_RELAY_IDENTITY_REJECTED$'):
            self.decrypt(receipt)
        with self.assertRaisesRegex(ValueError, '^PRIVATE_RELAY_INVALID_PIN$'):
            self.decrypt(receipt, expected_recipient_sha256=True)
        self.assertFalse((self.root / 'restored').exists())


if __name__ == '__main__':
    unittest.main()
