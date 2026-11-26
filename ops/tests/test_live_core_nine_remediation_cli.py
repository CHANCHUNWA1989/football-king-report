import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import test_live_core_nine_remediation as fixtures
from live_core_nine_remediation_cli import run_bundle


class NineBundleTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        f=fixtures.NineRemediationTests()
        f.setUp()
        d=f.d
        self.m=dict(schema="nine-core-private-history-v1",capture_rights_confirmed_by_operator=True,
                    primary_mapping=d.pm,secondary_mapping=d.mapping,prematch=d.prior,
                    markets=f.markets,quotes=None,context=None,cuts=[])
        for i,c in enumerate(f.cuts(),1):
            a,b=c["primary_raw"],c["secondary_raw"]
            (self.root/f"{i:02d}-api-football.json").write_bytes(a)
            (self.root/f"{i:02d}-sportmonks.json").write_bytes(b)
            self.m["cuts"].append(dict(now=c["now"],primary_clock=c["primary_clock"],
                secondary_clock=c["secondary_clock"],primary_sha256=hashlib.sha256(a).hexdigest(),
                secondary_sha256=hashlib.sha256(b).hexdigest()))

    def write(self):
        (self.root/"manifest.json").write_text(json.dumps(self.m),encoding="utf-8")

    def test_cli_bundle(self):
        self.write()
        r=run_bundle(self.root)
        self.assertEqual(r["research_status"],"RESEARCH_ONLY")
        self.assertEqual(r["scenario_count"],9)
        self.assertFalse(r["capture_rights_independently_verified"])
        self.assertEqual(r["production_recommendations"],"DISABLED")

    def test_tamper(self):
        self.write()
        (self.root/"02-api-football.json").write_bytes(b"{}")
        self.assertNotIn("scenarios",run_bundle(self.root))

    def test_rights_missing(self):
        self.m["capture_rights_confirmed_by_operator"]=False
        self.write()
        self.assertNotIn("scenarios",run_bundle(self.root))
