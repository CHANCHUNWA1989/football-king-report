import json
import tempfile
import unittest
from pathlib import Path
import test_live_core_durable_evidence as fixtures
from live_core_private_capture_runner import run_bundle,digest


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        d=fixtures.DualTests()
        d.setUp()
        a=json.dumps(d.primary).encode()
        b=d.raw()
        (self.root/"api-football.json").write_bytes(a)
        (self.root/"sportmonks.json").write_bytes(b)
        self.m=dict(schema="live-core-private-capture-v1",primary_sha256=digest(a),
                    secondary_sha256=digest(b),primary_mapping=d.pm,
                    secondary_mapping=d.mapping,primary_clock=d.clock,
                    secondary_clock=d.clock,decision_epoch=d.now,prematch=d.prior,
                    markets=[dict(market="totals",side="UNDER",line=2.25)],quotes=None,
                    capture_rights_confirmed_by_operator=True)

    def write(self):
        (self.root/"manifest.json").write_text(json.dumps(self.m),encoding="utf-8")

    def test_bundle(self):
        self.write()
        r=run_bundle(self.root)
        self.assertEqual(r["research_status"],"RESEARCH_ONLY")
        self.assertTrue(r["two_raw_payloads_parsed"])
        self.assertFalse(r["source_authenticated"])
        self.assertEqual(r["verified_forward_sample_credit"],0)
        self.assertEqual(r["production_recommendations"],"DISABLED")
        self.assertNotIn("xg_claim_same_cut",r)
        self.assertNotIn("quote_reviews",r)

    def test_modified_bytes(self):
        self.write()
        (self.root/"api-football.json").write_bytes(b"{}")
        self.assertNotIn("probabilities_1x2",run_bundle(self.root))

    def test_no_rights(self):
        self.m["capture_rights_confirmed_by_operator"]=False
        self.write()
        self.assertNotIn("probabilities_1x2",run_bundle(self.root))

    def test_missing_file(self):
        self.write()
        (self.root/"sportmonks.json").unlink()
        self.assertNotIn("probabilities_1x2",run_bundle(self.root))

    def test_wrong_manifest_schema(self):
        self.m["extra"]="not allowed"
        self.write()
        self.assertNotIn("probabilities_1x2",run_bundle(self.root))

    def test_duplicate_json_key(self):
        self.write()
        p=self.root/"manifest.json"
        p.write_text(p.read_text()[:-1]+',"schema":"live-core-private-capture-v1"}')
        self.assertNotIn("probabilities_1x2",run_bundle(self.root))
