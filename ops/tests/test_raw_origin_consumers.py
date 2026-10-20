"""V2 transport receipts must be replayed; legacy evidence is never upgraded."""
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ops.tests import test_raw_openligadb_identity_linkage as lineage_tests
from shadow_raw_source_collector import collect
from shadow_raw_ft_parser import convert

class RawOriginConsumerTests(unittest.TestCase):
    def setUp(self):
        self.fx = lineage_tests.RawOpenLigaDBIdentityLinkageTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.fx.raw_dir = self.fx.root / 'controlled-raw'
        raw = json.dumps(self.fx.raw).encode()
        def transport(url):
            return (raw if 'api.openligadb.de' in url else b'{"matches":[]}',
                    200, 'application/json', url)
        self.fx.manifest = collect(2026, self.fx.raw_dir, getter=transport,
                                  now=self.fx.fixture.options['now'])
    def test_controlled_receipts_link_without_authenticating_source_or_result(self):
        result, _ = self.fx.run_linkage()
        self.assertTrue(result['audit_completed'])
        self.assertEqual(result['linked_count'], 1)
        self.assertTrue(result['raw_origin_receipts_structurally_replayed'])
        self.fx.assert_held(result)
    def test_wrong_recorded_final_url_rejected_by_both_consumers(self):
        self.fx.manifest['sources'][0]['final_url'] = 'https://example.invalid/wrong'
        self.fx.write_manifest()
        result, _ = self.fx.run_linkage()
        self.assertFalse(result['audit_completed'])
        with self.assertRaisesRegex(ValueError, 'INVALID_RAW_ORIGIN_ENDPOINT|INVALID_RAW_ORIGIN_SUCCESS_RECEIPT'):
            convert(self.fx.raw_dir)
    def test_legacy_manifest_keeps_missing_receipts_and_no_origin_upgrade(self):
        m = self.fx.manifest
        m['schema'] = 'football-king-raw-ft-source-candidates-v1'
        m.pop('eligible_for_model_scoring')
        for source in m['sources']:
            for key in ['requested_utc', 'completed_utc', 'redirect_policy', 'final_url',
                        'http_status', 'content_type']:
                source.pop(key, None)
        self.fx.write_manifest()
        result, _ = self.fx.run_linkage()
        self.assertTrue(result['audit_completed'])
        self.assertFalse(result['raw_origin_receipts_structurally_replayed'])
        self.fx.assert_held(result)
