"""Plaintext originals stay private; authorized relay artifacts contain ciphertext only."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


def job(text, name):
    tail = text.split('\n  '+name+':\n', 1)[1]
    return re.split(r'\n  [a-z_]+:\n', tail, maxsplit=1)[0]


class PrivateArchiveWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT/'.github/workflows/private-all-market-research.yml').read_text()

    def test_collect_passes_only_safe_pins_to_another_job(self):
        producer = job(self.text, 'collect')
        header = producer.split('    steps:', 1)[0]
        self.assertNotIn('runner.temp', header)
        for name in ('private_capture_manifest_sha256', 'private_archive_blob_sha',
                     'private_archive_commit_sha', 'private_archive_sha256'):
            self.assertIn('      '+name+': ${{ steps.', header)
        self.assertNotIn('PRIVATE_ARCHIVE_TOKEN', header)
        self.assertIn('id: archive_private', producer)
        self.assertIn('ops.private_response_archive upload', producer)

    def test_cross_job_restore_has_no_provider_key_or_raw_public_upload(self):
        verifier = job(self.text, 'verify_private_original_archive')
        self.assertIn('    needs: collect', verifier)
        self.assertIn("needs.collect.outputs.private_archive_blob_sha != ''", verifier)
        self.assertIn('ops.private_response_archive restore', verifier)
        for flag in ('--expected-manifest-sha256', '--expected-blob-sha',
                     '--expected-commit-sha', '--expected-archive-sha256'):
            self.assertIn(flag, verifier)
        self.assertNotIn('THE_ODDS_API_KEY', verifier)
        self.assertNotIn('actions/upload-artifact@', verifier)
        self.assertNotIn('actions/cache@', verifier)
        self.assertNotIn('git push', verifier)
        self.assertIn('persist-credentials: false', verifier)

    def test_archive_credentials_are_scoped_to_transport_steps(self):
        producer = job(self.text, 'collect')
        steps = re.split(r'^      - ', producer, flags=re.M)
        archive = next(s for s in steps if 'id: archive_private' in s)
        for name in ('PRIVATE_ARCHIVE_REPOSITORY', 'PRIVATE_ARCHIVE_REPOSITORY_ID',
                     'PRIVATE_ARCHIVE_TOKEN'):
            self.assertIn(name+': ${{ secrets.'+name+' }}', archive)
            self.assertEqual(sum(name+':' in s for s in steps), 1)
        self.assertNotIn('THE_ODDS_API_KEY', archive)

    def test_existing_public_artifact_remains_exact_redacted_allowlist(self):
        producer = job(self.text, 'collect')
        uploads = [s for s in re.split(r'^      - ', producer, flags=re.M)
                   if 'uses: actions/upload-artifact@' in s]
        self.assertEqual(len(uploads), 3)
        block = re.search(r'          path: \|\n((?:            .+\n)+)', uploads[0])
        self.assertIsNotNone(block)
        self.assertEqual({s.strip() for s in block.group(1).splitlines()},
                         {'output/private_all_market_public_summary.json',
                          'output/recommendation_readiness.json'})

    def test_private_tests_gate_transport_sources_and_workflow(self):
        tests = (ROOT/'.github/workflows/private-market-tests.yml').read_text()
        for path in ('ops/private_response_archive.py',
                     'ops/tests/test_private_response_archive.py',
                     'ops/tests/test_private_archive_workflow.py',
                     'PRIVATE_DURABLE_ARCHIVE_2026_10_28.md'):
            self.assertEqual(tests.count("- '"+path+"'"), 2)
        self.assertIn('ops.tests.test_private_response_archive', tests)
        self.assertIn('ops.tests.test_private_archive_workflow', tests)


if __name__ == '__main__':
    unittest.main()
