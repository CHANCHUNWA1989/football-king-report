"""Explicitly authorized ciphertext publication preserves plaintext exclusions."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class PrivateRelayWorkflowTests(unittest.TestCase):
    def test_encryption_precedes_exact_ciphertext_and_receipt_uploads(self):
        text = (ROOT / '.github/workflows/private-all-market-research.yml').read_text()
        self.assertIn('ops.private_response_relay encrypt', text)
        self.assertIn('python -m ops.install_age', text)
        self.assertIn('sources/policies/private_original_recipient_v1.txt', text)
        self.assertNotIn('AGE-SECRET-KEY-', text)
        uploads = [s for s in re.split(r'^      - ', text, flags=re.M)
                   if 'uses: actions/upload-artifact@' in s]
        self.assertEqual(len(uploads), 3)
        expected = {
            'all-market-redacted-research-summary': {
                'output/private_all_market_public_summary.json', 'output/recommendation_readiness.json'},
            'football-private-original-ciphertext-${{ github.run_id }}-${{ github.run_attempt }}': {
                '${{ runner.temp }}/football-relay-ciphertext/original-response-pack.zip.age'},
            'football-private-original-receipt-${{ github.run_id }}-${{ github.run_attempt }}': {
                '${{ runner.temp }}/football-relay-receipt/producer-receipt.json'},
        }
        for step in uploads:
            name = re.search(r'^          name: (.+)$', step, re.M).group(1)
            self.assertIn(name, expected)
            match = re.search(r'^          path: \|\n((?:            .+\n)+)', step, re.M)
            self.assertIsNotNone(match)
            self.assertEqual({s.strip() for s in match.group(1).splitlines()}, expected.pop(name))
        self.assertEqual(expected, {})
        encrypt = next(s for s in re.split(r'^      - ', text, flags=re.M)
                       if 'ops.private_response_relay encrypt' in s)
        self.assertNotIn('secrets.', encrypt)
        self.assertIn('private_capture_manifest_sha256', encrypt)
        self.assertNotIn('continue-on-error', encrypt)

    def test_synthetic_workflow_has_no_provider_credentials_or_collector(self):
        text = (ROOT / '.github/workflows/private-original-relay-synthetic.yml').read_text()
        self.assertIn('CaptureSession', text)
        self.assertIn('SYNTHETIC_ONLY', text)
        self.assertIn('ops.private_response_relay encrypt', text)
        self.assertNotIn('secrets.', text)
        self.assertNotIn('ops.all_market_private_feed', text)
        self.assertNotIn('curl ', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('retention-days: 7', text)

    def test_real_crypto_tests_have_explicit_installed_binary(self):
        for name in ('private-market-tests.yml', 'football-king-ci.yml'):
            text = (ROOT / '.github/workflows' / name).read_text()
            self.assertIn('python -m ops.install_age', text)
            self.assertIn('FOOTBALL_AGE_BINARY=', text)
        private = (ROOT / '.github/workflows/private-market-tests.yml').read_text()
        for path in ('ops/private_response_relay.py', 'ops/private_relay_provenance.py',
                     'ops/install_age.py', 'ops/private_drive_handoff.py',
                     'ops/tests/test_private_drive_handoff.py', 'ops/tests/test_private_relay_workflow.py',
                     'sources/policies/private_original_recipient_v1.txt'):
            self.assertEqual(private.count("- '" + path + "'"), 2)


if __name__ == '__main__':
    unittest.main()
